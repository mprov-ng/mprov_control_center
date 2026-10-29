from networks.models import Network, SwitchPort
from networks.testing import NetworkTestCase
from systems.models import NetworkInterface, System, SystemBMC


class NetworkSummaryTabTests(NetworkTestCase):
  """ The network change page has a Network Summary tab listing the NICs and BMCs on that network. """

  def setUp(self):
    super().setUp()
    self.node = System.objects.create(hostname="node01", created_by=self.user)
    port = SwitchPort.objects.create(name="eth1", switch=self.switch("sw01", self.mgmt))
    NetworkInterface.objects.create(system=self.node, name="ens18", mac="bc:24:11:00:00:01",
                                    ipaddress="172.16.0.11", network=self.lan, switch_port=port, bootable=True)
    NetworkInterface.objects.create(system=self.node, name="ens19", network=self.lan)
    SystemBMC.objects.create(system=self.node, ipaddress="172.16.1.11", mac="bc:24:11:00:00:02", network=self.lan)
    node02 = System.objects.create(hostname="node02", created_by=self.user)
    NetworkInterface.objects.create(system=node02, name="ens18", ipaddress="172.16.0.5", network=self.lan)
    other = System.objects.create(hostname="elsewhere", created_by=self.user)
    NetworkInterface.objects.create(system=other, name="ens18", ipaddress="10.0.0.9", network=self.mgmt)

  def summary(self, network, query=""):
    response = self.client.get(f"/admin/networks/network/{network.pk}/change/{query}")
    self.assertEqual(response.status_code, 200)
    return response.content.decode()

  def test_lists_nics_and_bmcs_with_links_to_their_system(self):
    html = self.summary(self.lan)
    self.assertIn('href="#network-summary-tab"', html)
    change = f"/admin/systems/system/{self.node.pk}/change/"
    # NIC rows open the system's Network Interfaces tab, the BMC row its System BMCs tab.
    self.assertEqual(html.count(f'<a href="{change}#network-interfaces-tab">node01</a>'), 2)
    self.assertEqual(html.count(f'<a href="{change}#system-bmcs-tab">node01</a>'), 1)
    self.assertInHTML("<td>ens18</td><td>bc:24:11:00:00:01</td><td>172.16.0.11</td><td>sw01/eth1</td><td>Yes</td>", html)
    self.assertInHTML('<td><span class="badge bg-info">BMC</span></td><td>bc:24:11:00:00:02</td>'
                      "<td>172.16.1.11</td><td>N/A</td><td>N/A</td>", html)

  def test_system_page_has_the_tabs_the_links_open(self):
    response = self.client.get(f"/admin/systems/system/{self.node.pk}/change/")
    self.assertContains(response, 'href="#network-interfaces-tab"')
    self.assertContains(response, 'href="#system-bmcs-tab"')

  def test_empty_fields_show_na(self):
    self.assertInHTML("<td>ens19</td><td>N/A</td><td>N/A</td><td>N/A</td><td>No</td>", self.summary(self.lan))

  def test_leaves_out_other_networks(self):
    self.assertNotIn("elsewhere", self.summary(self.lan))
    self.assertIn("elsewhere", self.summary(self.mgmt))

  def order(self, html, *cells):
    positions = [html.index(cell) for cell in cells]
    self.assertEqual(positions, sorted(positions))

  def test_sorted_by_hostname_then_nic_by_default(self):
    html = self.summary(self.lan)
    self.order(html, "<td>172.16.0.11</td>", "<td>ens19</td>", "<td>172.16.1.11</td>", "<td>172.16.0.5</td>")
    self.assertIn('href="?summary_sort=ip#network-summary-tab"', html)

  def test_sorted_by_ip_address(self):
    html = self.summary(self.lan, "?summary_sort=ip")
    # numeric order, not string order (.0.11 sorts before .0.5 as text); NICs without an IP go last.
    self.order(html, "<td>172.16.0.5</td>", "<td>172.16.0.11</td>", "<td>172.16.1.11</td>", "<td>ens19</td>")

  def test_empty_network(self):
    network = Network.objects.create(name="Empty", net_type=self.net_type, subnet="192.168.9.0", netmask=24)
    self.assertIn("No systems on this network.", self.summary(network))

  def test_no_summary_tab_when_adding(self):
    response = self.client.get("/admin/networks/network/add/")
    self.assertEqual(response.status_code, 200)
    self.assertNotIn("#network-summary-tab", response.content.decode())
