from django.contrib.auth.models import User
from django.test import TestCase

from systems.models import System, SystemGroup, NetworkInterface


class SystemBulkUpdateTests(TestCase):
  """ The "Update fields on multiple systems" admin action. """

  def setUp(self):
    self.user = User.objects.create_superuser("admin", "admin@example.com", "password")
    self.client.force_login(self.user)
    self.system = System.objects.create(hostname="bulk-node", created_by=self.user)
    self.nic = NetworkInterface.objects.create(system=self.system, name="eth0", bootable=True)

  def bulk_update(self, **data):
    data.update({"action": "bulk_update", "_selected_action": [self.system.pk], "form-post": "1"})
    response = self.client.post("/admin/systems/system/", data, follow=True)
    self.assertEqual(response.status_code, 200)
    return [str(m) for m in response.context["messages"]]

  def test_clearing_provision(self):
    self.bulk_update(update_provision="on")
    self.system.refresh_from_db()
    self.assertFalse(self.system.provision)
    # the boot NIC is left alone.
    self.nic.refresh_from_db()
    self.assertTrue(self.nic.bootable)

  def test_setting_provision(self):
    self.system.provision = False
    self.system.save()
    messages = self.bulk_update(update_provision="on", provision="on")
    self.system.refresh_from_db()
    self.assertTrue(self.system.provision)
    self.assertIn("Changed fields on 1 items", messages)

  def test_set_bootable_option_is_gone(self):
    response = self.client.post("/admin/systems/system/", {"action": "bulk_update", "_selected_action": [self.system.pk]})
    self.assertNotContains(response, "set_bootable")
    self.assertContains(response, 'name="update_provision"')

  def test_many_to_many_field(self):
    group = SystemGroup.objects.create(name="compute")
    self.bulk_update(update_systemgroups="on", systemgroups=[group.pk])
    self.assertEqual(list(self.system.systemgroups.all()), [group])
