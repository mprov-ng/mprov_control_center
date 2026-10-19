from common.testing import APITestCase
from networks.models import Network, NetworkType, Switch


class NetworkTestCase(APITestCase):
  """ An APITestCase with two networks, lan and mgmt, and a helper to add switches. """

  def setUp(self):
    super().setUp()
    self.net_type = NetworkType.objects.create(name="Ethernet")
    self.lan = Network.objects.create(name="Cluster LAN", net_type=self.net_type, subnet="172.16.0.0", netmask=16)
    self.mgmt = Network.objects.create(name="Mgmt", net_type=self.net_type, subnet="10.0.0.0", netmask=8)

  def switch(self, hostname, network):
    return Switch.objects.create(hostname=hostname, network=network, mgmt_ip="10.0.0.1",
                                 mgmt_mac="de:ad:be:ef:00:01", created_by=self.user)
