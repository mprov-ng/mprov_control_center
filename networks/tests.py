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
