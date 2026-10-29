from unittest import mock

from django.contrib.auth.models import User
from django.test import TestCase

from disklayouts.models import DiskLayout, DiskPartition
from systems.models import System, NetworkInterface, SystemBMC
from systems.views import SystemPowerAPIView

NO_BOOT_PART = "none of its disk layouts has a bootable partition"


class BootDiskTestCase(TestCase):
  """ A stateful system with a boot disk and a data disk, as the installer expects (#361). """

  def setUp(self):
    self.user = User.objects.create_superuser("admin", "admin@example.com", "password")
    self.client.force_login(self.user)
    self.system = System.objects.create(hostname="disk-node", created_by=self.user, stateful=True, provision=False)
    NetworkInterface.objects.create(system=self.system, name="eth0", ipaddress="10.0.0.40", bootable=True)
    self.root = self.layout("root", "/dev/sda")
    self.boot_part = DiskPartition.objects.create(disklayout=self.root, partnum=1, mount="/", size=1024, filesystem="xfs", bootable=True)
    self.data = self.layout("data", "/dev/sdb")
    DiskPartition.objects.create(disklayout=self.data, partnum=1, mount="/data", size=1024, filesystem="xfs")

  def layout(self, name, diskname):
    layout = DiskLayout.objects.create(name=name, diskname=diskname)
    layout.systems.add(self.system)
    return layout


class BootDiskProblemTests(BootDiskTestCase):

  def test_one_boot_disk_and_a_data_disk_is_fine(self):
    self.assertIsNone(self.system.boot_disk_problem())

  def test_no_bootable_partition(self):
    self.boot_part.bootable = False
    self.boot_part.save()
    self.assertIn(NO_BOOT_PART, self.system.boot_disk_problem())

  def test_two_boot_disks(self):
    DiskPartition.objects.filter(disklayout=self.data).update(bootable=True)
    problem = self.system.boot_disk_problem()
    self.assertIn("more than one", problem)
    self.assertIn("data, root", problem)

  def test_no_disk_layouts(self):
    self.system.disks.clear()
    self.assertIn("has no disk layouts", self.system.boot_disk_problem())

  def test_a_diskless_system_needs_no_boot_disk(self):
    self.system.disks.clear()
    self.system.stateful = False
    self.system.save()
    self.assertIsNone(self.system.boot_disk_problem())


class PXEBootRefusesBadBootDiskTests(BootDiskTestCase):
  """ PXE Boot refuses a stateful system the installer would reject, before resetting it. """

  def setUp(self):
    super().setUp()
    self.bmc = SystemBMC.objects.create(system=self.system, ipaddress="10.0.2.40", username="admin", password="pw")
    patcher = mock.patch.object(SystemPowerAPIView, "_doPowerCmd", return_value={"status": 200})
    self.power = patcher.start()
    self.addCleanup(patcher.stop)

  def pxe(self):
    return self.client.get(f"/power/pxe/?id={self.system.id}", CONTENT_TYPE="application/json")

  def test_good_layouts_pxe_boot(self):
    self.assertEqual(self.pxe().status_code, 200)
    self.system.refresh_from_db()
    self.assertTrue(self.system.provision)

  def test_no_bootable_partition_is_a_409(self):
    self.boot_part.bootable = False
    self.boot_part.save()
    response = self.pxe()
    self.assertEqual(response.status_code, 409)
    self.assertIn(NO_BOOT_PART, response.json()["details"])
    self.assertIn("It was not reset.", response.json()["details"])
    self.power.assert_not_called()
    self.system.refresh_from_db()
    self.assertFalse(self.system.provision)

  def test_admin_action_reports_it(self):
    self.boot_part.bootable = False
    self.boot_part.save()
    with mock.patch("systems.admin.SystemAdmin._doPowerCmd") as power:
      response = self.client.post("/admin/systems/system/", {"action": "sys_pxe", "_selected_action": [self.system.pk]}, follow=True)
    power.assert_not_called()
    messages = [str(m) for m in response.context["messages"]]
    self.assertTrue(any(NO_BOOT_PART in m and "not reset" in m for m in messages), messages)


class BootDiskAdminWarningTests(BootDiskTestCase):
  """ Saving a layout or bulk-updating systems warns, but still saves, when the installer would refuse a system. """

  def save_layout(self, layout, systems, bootable):
    part = layout.partitions.get()
    data = {
      "name": layout.name, "diskname": layout.diskname, "systems": [s.pk for s in systems],
      "partitions-TOTAL_FORMS": "1", "partitions-INITIAL_FORMS": "1",
      "partitions-MIN_NUM_FORMS": "0", "partitions-MAX_NUM_FORMS": "1000",
      "partitions-0-id": part.pk, "partitions-0-disklayout": layout.pk, "partitions-0-partnum": part.partnum,
      "partitions-0-mount": part.mount, "partitions-0-size": part.size, "partitions-0-filesystem": part.filesystem,
      "partitions-0-format": "on", "_save": "Save",
    }
    if bootable:
      data["partitions-0-bootable"] = "on"
    response = self.client.post(f"/admin/disklayouts/disklayout/{layout.pk}/change/", data, follow=True)
    self.assertEqual(response.status_code, 200)
    return [str(m) for m in response.context["messages"]]

  def test_clearing_the_boot_partition_warns_but_saves(self):
    messages = self.save_layout(self.root, [self.system], bootable=False)
    self.assertTrue(any(NO_BOOT_PART in m for m in messages), messages)
    self.boot_part.refresh_from_db()
    self.assertFalse(self.boot_part.bootable)

  def test_a_good_layout_does_not_warn(self):
    messages = self.save_layout(self.root, [self.system], bootable=True)
    self.assertFalse(any("stateful" in m for m in messages), messages)

  def test_detaching_the_boot_disk_warns_about_that_system(self):
    messages = self.save_layout(self.root, [], bootable=True)
    self.assertTrue(any(f"disk-node is stateful but {NO_BOOT_PART[:4]}" in m for m in messages), messages)

  def test_bulk_update_to_stateful_warns(self):
    other = System.objects.create(hostname="no-disks", created_by=self.user)
    data = {"action": "bulk_update", "_selected_action": [other.pk], "form-post": "1",
            "update_stateful": "on", "stateful": "on"}
    response = self.client.post("/admin/systems/system/", data, follow=True)
    messages = [str(m) for m in response.context["messages"]]
    self.assertTrue(any("no-disks is stateful but has no disk layouts" in m for m in messages), messages)
    other.refresh_from_db()
    self.assertTrue(other.stateful)
