from django.test import SimpleTestCase

from networks.models import Network
from networks.testing import NetworkTestCase
from networks.utils import calculate_new_ip, calculate_new_ips, update_associated_ips
from systems.models import NetworkInterface, System, SystemBMC


class CalculateNewIPTests(SimpleTestCase):
  """ calculate_new_ip keeps the address bits the new netmask leaves for hosts. """

  def new_ip(self, ip, old, new):
    net = lambda cidr: Network(subnet=cidr.split("/")[0], netmask=int(cidr.split("/")[1]))
    return calculate_new_ip(ip, net(old), net(new))

  def test_octet_boundary(self):
    self.assertEqual(self.new_ip("10.0.1.5", "10.0.1.0/24", "10.0.2.0/24"), "10.0.2.5")

  def test_non_octet_masks_keep_hosts_distinct(self):
    self.assertEqual(self.new_ip("172.16.17.5", "172.16.16.0/20", "172.16.32.0/20"), "172.16.33.5")
    self.assertEqual(self.new_ip("172.16.18.5", "172.16.16.0/20", "172.16.32.0/20"), "172.16.34.5")
    self.assertEqual(self.new_ip("10.0.0.130", "10.0.0.128/25", "10.0.1.0/25"), "10.0.1.2")

  def test_growing_keeps_the_new_masks_host_bits(self):
    self.assertEqual(self.new_ip("172.16.1.5", "172.16.1.0/24", "10.1.0.0/16"), "10.1.1.5")

  def test_shrinking_keeps_the_low_bits(self):
    self.assertEqual(self.new_ip("10.0.5.5", "10.0.0.0/16", "192.168.1.0/24"), "192.168.1.5")

  def test_network_or_broadcast_address_is_none(self):
    self.assertIsNone(self.new_ip("10.0.1.0", "10.0.0.0/16", "192.168.1.0/24"))
    self.assertIsNone(self.new_ip("10.0.1.255", "10.0.0.0/16", "192.168.1.0/24"))

  def test_ipv6(self):
    self.assertEqual(self.new_ip("fd00:1::5", "fd00:1::/64", "fd00:2::/64"), "fd00:2::5")

  def test_netmask_as_a_string(self):
    self.assertEqual(calculate_new_ip("10.0.1.5", Network(subnet="10.0.1.0", netmask="24"),
                                      Network(subnet="10.0.9.0", netmask=24)), "10.0.9.5")


class CalculateNewIPsTests(SimpleTestCase):
  """ calculate_new_ips maps a network's addresses together and won't create duplicates. """

  def test_collisions_are_none(self):
    old, new = Network(subnet="10.0.0.0", netmask=16), Network(subnet="192.168.1.0", netmask=24)
    new_ips = calculate_new_ips(["10.0.1.5", "10.0.2.5", "10.0.2.6", None, ""], old, new)
    self.assertEqual(new_ips, {"10.0.1.5": None, "10.0.2.5": None, "10.0.2.6": "192.168.1.6"})

  def test_same_address_twice_is_not_a_collision(self):
    old, new = Network(subnet="10.0.1.0", netmask=24), Network(subnet="10.0.2.0", netmask=24)
    self.assertEqual(calculate_new_ips(["10.0.1.5", "10.0.1.5"], old, new), {"10.0.1.5": "10.0.2.5"})


class UpdateAssociatedIPsTests(NetworkTestCase):
  """ update_associated_ips moves a network's NICs and BMCs, and reports the ones it can't. """

  def test_shrink_moves_unique_addresses_and_reports_collisions(self):
    system = System.objects.create(hostname="node", created_by=self.user)
    nics = {ip: NetworkInterface.objects.create(system=system, name=f"eth{i}", ipaddress=ip, network=self.lan)
            for i, ip in enumerate(["172.16.1.5", "172.16.2.5", "172.16.2.6"])}
    SystemBMC.objects.create(system=system, ipaddress="172.16.3.7", network=self.lan)
    self.lan.subnet, self.lan.netmask = "10.9.9.0", 24
    self.lan.save()
    results = update_associated_ips(self.lan, "172.16.0.0", 16)
    self.assertEqual((results["interfaces_updated"], results["bmcs_updated"], len(results["errors"])), (1, 1, 2))
    current = {ip: NetworkInterface.objects.get(pk=nic.pk).ipaddress for ip, nic in nics.items()}
    self.assertEqual(current, {"172.16.1.5": "172.16.1.5", "172.16.2.5": "172.16.2.5", "172.16.2.6": "10.9.9.6"})
    self.assertEqual(SystemBMC.objects.get().ipaddress, "10.9.9.7")
