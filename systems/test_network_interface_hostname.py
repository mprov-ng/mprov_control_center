from django.contrib.auth.models import User
from django.test import TestCase

from systems.models import NetworkInterface, System


class NetworkInterfaceHostnameTests(TestCase):
  """ NetworkInterface.hostname defaults from the parent System only when it is
  empty; a hostname an operator sets on the interface row survives saves.
  Regression test for mprov-ng/mprov_control_center#322. """

  def setUp(self):
    self.user = User.objects.create_user("tester")
    self.system = System.objects.create(hostname="node-01", created_by=self.user)

  def test_hostname_defaults_from_system_on_create(self):
    """ A new interface with no hostname inherits the system hostname. """
    nic = NetworkInterface.objects.create(system=self.system, name="eth0")
    self.assertEqual(nic.hostname, "node-01")

  def test_user_set_hostname_survives_repeated_save(self):
    """ A user-set interface hostname is not overwritten by later saves. """
    nic = NetworkInterface.objects.create(system=self.system, name="eth1",
                                          hostname="eth1-label")
    self.assertEqual(nic.hostname, "eth1-label")
    nic.mtu = 9000
    nic.save()
    nic.refresh_from_db()
    self.assertEqual(nic.hostname, "eth1-label")
    self.assertEqual(nic.mtu, 9000)

  def test_blank_hostname_defaults_from_system_on_save(self):
    """ Clearing the hostname makes the next save re-default it from the system. """
    nic = NetworkInterface.objects.create(system=self.system, name="eth2")
    nic.hostname = None
    nic.save()
    nic.refresh_from_db()
    self.assertEqual(nic.hostname, "node-01")
