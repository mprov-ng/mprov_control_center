from django.contrib.auth.models import User
from django.test import TestCase

from systems.models import System, NetworkInterface


class NetworkInterfaceNetworkFilterTests(TestCase):
  """ GET /networkinterfaces/?network=SLUG reconciles NIC networks with switch port networks. """

  def setUp(self):
    from networks.models import Network, NetworkType, Switch, SwitchPort
    self.user = User.objects.create_superuser("admin", "admin@example.com", "password")
    self.client.force_login(self.user)
    net_type = NetworkType.objects.create(name="Ethernet")
    self.lan = Network.objects.create(name="Cluster LAN", net_type=net_type, subnet="172.16.0.0", netmask=16)
    self.mgmt = Network.objects.create(name="Mgmt", net_type=net_type, subnet="10.0.0.0", netmask=8)
    switch = Switch.objects.create(hostname="sw1", mgmt_ip="10.0.0.1", mgmt_mac="de:ad:be:ef:00:01", created_by=self.user)
    self.system = System.objects.create(hostname="node", created_by=self.user)
    def port(name, net):
      return SwitchPort.objects.create(name=name, switch=switch, networks=net)
    self.nic("direct", self.lan, None)
    self.nic("other-port-1", self.lan, port("1", self.mgmt))
    self.nic("other-port-2", self.lan, port("2", self.mgmt))
    self.nic("port-only", None, port("3", self.lan))
    self.nic("both", self.lan, port("4", self.lan))

  def nic(self, name, network, switch_port):
    return NetworkInterface.objects.create(system=self.system, name=name, network=network, switch_port=switch_port)

  def get_json(self, url):
    return self.client.get(url, CONTENT_TYPE="application/json")

  def test_switch_port_takes_precedence(self):
    response = self.get_json("/networkinterfaces/?network=cluster-lan")
    self.assertEqual(response.status_code, 200)
    nics = {nic["name"]: nic for nic in response.json()}
    self.assertEqual(sorted(nics), ["both", "direct", "port-only"])
    self.assertEqual({nic["network"] for nic in nics.values()}, {self.lan.pk})

  def test_unknown_network_is_404(self):
    self.assertEqual(self.get_json("/networkinterfaces/?network=nope").status_code, 404)
