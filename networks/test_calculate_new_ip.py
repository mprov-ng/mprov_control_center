from django.test import SimpleTestCase

from networks.models import Network
from networks.utils import calculate_new_ip


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
