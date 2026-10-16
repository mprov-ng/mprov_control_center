from unittest import mock

from common.testing import APITestCase
from networks.models import Network, NetworkType, Switch


class NetworkTestCase(APITestCase):

  def setUp(self):
    super().setUp()
    self.net_type = NetworkType.objects.create(name="Ethernet")
    self.lan = Network.objects.create(name="Cluster LAN", net_type=self.net_type, subnet="172.16.0.0", netmask=16)
    self.mgmt = Network.objects.create(name="Mgmt", net_type=self.net_type, subnet="10.0.0.0", netmask=8)

  def switch(self, hostname, network):
    return Switch.objects.create(hostname=hostname, network=network, mgmt_ip="10.0.0.1",
                                 mgmt_mac="de:ad:be:ef:00:01", created_by=self.user)


class SwitchAPIViewTests(NetworkTestCase):
  """ /switches/ returns one switch by primary key, or switches filtered by network slug. """

  def test_detail_returns_one_switch(self):
    self.switch("sw1", self.lan)
    sw2 = self.switch("sw2", self.lan)
    response = self.get_json(f"/switches/{sw2.pk}/")
    self.assertEqual(response.status_code, 200)
    self.assertEqual(response.json()["hostname"], "sw2")

  def test_network_slug_filter(self):
    self.switch("sw1", self.lan)
    self.switch("sw2", self.mgmt)
    response = self.get_json("/switches/?network=cluster-lan")
    self.assertEqual(response.status_code, 200)
    self.assertEqual([s["hostname"] for s in response.json()], ["sw1"])

  def test_network_with_no_switches_is_an_empty_list(self):
    response = self.get_json("/switches/?network=cluster-lan")
    self.assertEqual(response.status_code, 200)
    self.assertEqual(response.json(), [])

  def test_unknown_network_is_404(self):
    self.assertEqual(self.get_json("/switches/?network=nope").status_code, 404)

  def test_docs_page(self):
    response = self.client.get("/switches/")
    self.assertEqual(response.status_code, 200)
    self.assertTrue(response["Content-Type"].startswith("text/html"))
    self.assertIn("<h1>/switches/</h1>", response.content.decode())


class NetworkSubnetChangeTests(NetworkTestCase):
  """ Changing a network's subnet in the admin goes through a confirmation page that applies the whole edit. """

  def change(self, **changes):
    data = {"name": self.lan.name, "net_type": self.net_type.pk, "vlan": self.lan.vlan, "subnet": self.lan.subnet,
            "netmask": self.lan.netmask, "domain": "", "_save": "Save"}
    data.update(changes)
    response = self.client.post(f"/admin/networks/network/{self.lan.pk}/change/", data)
    self.assertRedirects(response, f"/admin/networks/network/{self.lan.pk}/update-with-confirmation/",
                         fetch_redirect_response=False)
    return self.client.post(response["Location"], {"confirm_update": "1"}, follow=True)

  def test_other_fields_are_saved_with_the_subnet(self):
    other_type = NetworkType.objects.create(name="Infiniband")
    self.change(subnet="172.17.0.0", vlan=42, net_type=other_type.pk, isdhcp="on")
    self.lan.refresh_from_db()
    self.assertEqual((self.lan.subnet, self.lan.vlan, self.lan.net_type, self.lan.isdhcp),
                     ("172.17.0.0", 42, other_type, True))

  def test_ip_errors_are_a_warning(self):
    with mock.patch("networks.utils.update_associated_ips",
                    return_value={"interfaces_updated": 0, "bmcs_updated": 0, "errors": ["nic1: no IP"]}):
      response = self.change(subnet="172.17.0.0")
    messages = {(m.level_tag, str(m)) for m in response.context["messages"]}
    self.assertIn(("success", "Network updated successfully. "), messages)
    self.assertIn(("warning", "Errors updating IPs: nic1: no IP"), messages)
