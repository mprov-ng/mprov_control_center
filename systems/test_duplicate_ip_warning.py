from django.contrib import messages
from django.contrib.auth.models import User
from django.test import TestCase

from systems.admin import warn_duplicate_ip_assignments
from systems.models import System, NetworkInterface


class FakeModelAdmin:
  """ Records message_user() calls instead of needing a real request/response. """

  def __init__(self):
    self.calls = []

  def message_user(self, request, message, level=None):
    self.calls.append((message, level))


class DuplicateIPWarningTests(TestCase):
  """ Saving a System with a NIC IP already used elsewhere warns, but doesn't block the save (#373). """

  def setUp(self):
    self.user = User.objects.create_superuser("admin", "admin@example.com", "password")
    self.sys1 = System.objects.create(hostname="node01", created_by=self.user)
    self.sys2 = System.objects.create(hostname="node02", created_by=self.user)
    self.admin = FakeModelAdmin()

  def test_warns_when_another_system_already_has_the_ip(self):
    NetworkInterface.objects.create(system=self.sys1, name="eth0", ipaddress="10.0.0.5")
    NetworkInterface.objects.create(system=self.sys2, name="eth0", ipaddress="10.0.0.5")

    warn_duplicate_ip_assignments(self.admin, None, [self.sys2])

    self.assertEqual(len(self.admin.calls), 1)
    message, level = self.admin.calls[0]
    self.assertIn("10.0.0.5", message)
    self.assertIn("node01", message)
    self.assertIn("eth0", message)
    self.assertEqual(level, messages.WARNING)

  def test_no_warning_for_a_unique_ip(self):
    NetworkInterface.objects.create(system=self.sys1, name="eth0", ipaddress="10.0.0.5")
    NetworkInterface.objects.create(system=self.sys2, name="eth0", ipaddress="10.0.0.6")

    warn_duplicate_ip_assignments(self.admin, None, [self.sys2])

    self.assertEqual(self.admin.calls, [])

  def test_no_warning_without_an_ip(self):
    NetworkInterface.objects.create(system=self.sys2, name="eth0", ipaddress=None)

    warn_duplicate_ip_assignments(self.admin, None, [self.sys2])

    self.assertEqual(self.admin.calls, [])

  def test_no_warning_for_the_systems_own_other_nic(self):
    # Two NICs on the same system sharing an IP isn't "another system" using it.
    NetworkInterface.objects.create(system=self.sys2, name="eth0", ipaddress="10.0.0.5")
    NetworkInterface.objects.create(system=self.sys2, name="eth1", ipaddress="10.0.0.5")

    warn_duplicate_ip_assignments(self.admin, None, [self.sys2])

    self.assertEqual(self.admin.calls, [])
