import json
from unittest import mock

from django.test import SimpleTestCase
from rest_framework.permissions import IsAuthenticated

from common.testing import APITestCase
from networks.api_views import update_network_with_confirmation
from networks.models import Network, NetworkType, Switch
from networks.utils import calculate_new_ip


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


class NetworkUpdateWithConfirmationAPITests(NetworkTestCase):
  """ POST /networks/<pk>/update-with-confirmation/ asks before a subnet change. """

  def setUp(self):
    super().setUp()
    # The project default needs a login and an API key; a login is enough here.
    patcher = mock.patch.object(update_network_with_confirmation.cls, "permission_classes", [IsAuthenticated])
    patcher.start()
    self.addCleanup(patcher.stop)

  def post(self, body):
    return self.client.post(f"/networks/{self.lan.pk}/update-with-confirmation/", body, content_type="application/json")

  def test_same_netmask_as_a_string_is_not_a_change(self):
    response = self.post(json.dumps({"network_data": {"netmask": "16", "domain": "cluster"}}))
    self.assertEqual(response.status_code, 200)
    self.assertNotIn("requires_confirmation", response.json())
    self.lan.refresh_from_db()
    self.assertEqual(self.lan.domain, "cluster")

  def test_subnet_change_asks_first(self):
    response = self.post(json.dumps({"network_data": {"subnet": "172.17.0.0"}}))
    self.assertEqual(response.status_code, 200)
    self.assertTrue(response.json()["requires_confirmation"])
    self.lan.refresh_from_db()
    self.assertEqual(self.lan.subnet, "172.16.0.0")

  def test_non_object_body_is_400(self):
    for body in ("[]", '"x"', json.dumps({"network_data": []})):
      self.assertEqual(self.post(body).status_code, 400, body)


class CalculateNewIPTests(SimpleTestCase):
  """ calculate_new_ip keeps an address's host part when its network moves. """

  def new_ip(self, ip, old, new):
    net = lambda cidr: Network(subnet=cidr.split("/")[0], netmask=int(cidr.split("/")[1]))
    return calculate_new_ip(ip, net(old), net(new))

  def test_octet_boundary(self):
    self.assertEqual(self.new_ip("10.0.1.5", "10.0.1.0/24", "10.0.2.0/24"), "10.0.2.5")

  def test_non_octet_masks_keep_hosts_distinct(self):
    self.assertEqual(self.new_ip("172.16.17.5", "172.16.16.0/20", "172.16.32.0/20"), "172.16.33.5")
    self.assertEqual(self.new_ip("172.16.18.5", "172.16.16.0/20", "172.16.32.0/20"), "172.16.34.5")
    self.assertEqual(self.new_ip("10.0.0.130", "10.0.0.128/25", "10.0.1.0/25"), "10.0.1.2")

  def test_host_that_does_not_fit_is_none(self):
    self.assertIsNone(self.new_ip("10.0.5.5", "10.0.0.0/16", "192.168.1.0/24"))

  def test_netmask_as_a_string(self):
    self.assertEqual(calculate_new_ip("10.0.1.5", Network(subnet="10.0.1.0", netmask="24"),
                                      Network(subnet="10.0.9.0", netmask=24)), "10.0.9.5")
