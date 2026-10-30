import importlib.util
import sys
import types
from pathlib import Path
from unittest import mock

from django.conf import settings
from django.test import SimpleTestCase


def fake_parted():
  """ Just enough of pyparted for buildDisks() and _createPartition(). """
  parted = types.ModuleType("parted")
  parted.PARTITION_NORMAL = 0
  parted.PARTITION_SWAP = 3
  parted.PARTITION_RAID = 5
  parted.PARTITION_BIOS_GRUB = 12
  parted.DISK_GPT_PMBR_BOOT = 1
  parted.partitionFlag = {3: 'swap', 5: 'raid', 12: 'bios_grub', 18: 'esp'}
  parted.getDevice = lambda path: mock.Mock(path=path, sectorSize=512, **{"getLength.return_value": 67108864})
  parted.freshDisk = lambda device, label: mock.Mock()
  parted.Geometry = mock.Mock
  parted.FileSystem = mock.Mock
  parted.Partition = mock.Mock
  return parted


def disk(slug, diskname, *partitions):
  return {"slug": slug, "diskname": diskname, "dtype": "scsi", "partitions": [
    {"mount": "/", "size": 0, "fill": False, "filesystem": "xfs", "bootable": False, **p} for p in partitions]}


class StatefulInstallerTestCase(SimpleTestCase):
  """ Loads static/mprov_stateful.py with fake parted and sh, and runs buildDisks()/buildRAIDs(). """

  def setUp(self):
    path = Path(settings.BASE_DIR) / "static" / "mprov_stateful.py"
    spec = importlib.util.spec_from_file_location("mprov_stateful_under_test", path)
    self.module = importlib.util.module_from_spec(spec)
    self.sh = mock.MagicMock()
    with mock.patch.dict(sys.modules, {"parted": fake_parted(), "sh": self.sh}):
      spec.loader.exec_module(self.module)
    # skip __init__, which loads the node's config.
    self.installer = self.module.mProvStatefulInstaller.__new__(self.module.mProvStatefulInstaller)

  def build(self, *layout):
    self.installer.disklayout = list(layout)
    self.fstab = mock.mock_open()
    with mock.patch.object(self.installer, "_getDiskLayout"), \
         mock.patch.object(self.installer, "_checkDisks"), \
         mock.patch.object(self.installer, "_waitForPartition") as self.wait, \
         mock.patch.object(self.module.time, "sleep"), \
         mock.patch("builtins.open", self.fstab):
      self.installer.buildDisks()
      self.installer.buildRAIDs()

  def fstab_lines(self):
    return "".join(c.args[0] for c in self.fstab().write.call_args_list).splitlines()

  def formatted(self):
    """ The device each mkfs/mkswap ran on. """
    # the EFI mkfs gets one list, the others separate args ending with the device.
    devices = [c.args[0][-1] if isinstance(c.args[0], list) else c.args[-1] for c in self.sh.mkfs.call_args_list]
    devices += [c.args[0] for c in self.sh.mkswap.call_args_list]
    return sorted(devices)



class StatefulPartitionDeviceTests(StatefulInstallerTestCase):
  """ static/mprov_stateful.py formats, and builds RAIDs on, the device each layout partition really got. """

  def test_fill_partition_is_created_last(self):
    # the layout from the 2026-10-28 rig test: / fills, and is partition 1.
    root = disk("root", "/dev/sda",
                {"partnum": 1, "mount": "/", "fill": True, "bootable": True},
                {"partnum": 2, "mount": "swap", "size": 1024, "filesystem": "linux-swap"},
                {"partnum": 3, "mount": "/scratch", "size": 2048})
    self.build(root)
    # sda1 biosboot, sda2 EFI, then swap, /scratch, and / last.
    self.assertEqual(self.installer.partDevices, {("root", 2): "/dev/sda3", ("root", 3): "/dev/sda4", ("root", 1): "/dev/sda5"})
    self.sh.mkswap.assert_called_once()
    self.assertEqual(self.sh.mkswap.call_args.args[0], "/dev/sda3")
    self.assertEqual(self.formatted(), ["/dev/sda2", "/dev/sda3", "/dev/sda4", "/dev/sda5"])

  def test_each_disk_numbers_from_one(self):
    self.build(disk("root", "/dev/sda", {"partnum": 1, "mount": "/", "fill": True, "bootable": True}),
               disk("data", "/dev/nvme0n1", {"partnum": 1, "mount": "/data", "fill": True}))
    self.assertEqual(self.installer.partDevices, {("root", 1): "/dev/sda3", ("data", 1): "/dev/nvme0n1p1"})

  def test_raid_members_use_their_partitions_devices(self):
    md = {"slug": "md0", "diskname": "/dev/md0", "dtype": "mdrd", "raidlevel": 1, "filesystem": "xfs", "mount": "/data", "partitions": [],
          "members": [{"disklayout": "root", "partnum": 1}, {"disklayout": "second", "partnum": 1}]}
    self.build(disk("root", "/dev/sda",
                    {"partnum": 1, "mount": "raid", "size": 4096, "filesystem": "raid"},
                    {"partnum": 2, "mount": "/", "fill": True, "bootable": True}),
               disk("second", "/dev/sdb", {"partnum": 1, "mount": "raid", "size": 4096, "filesystem": "raid"}),
               md)
    create = [c.args[0] for c in self.sh.mdadm.call_args_list if "--create" in c.args[0]]
    self.assertEqual(len(create), 1)
    self.assertEqual(create[0][-2:], ["/dev/sda3", "/dev/sdb1"])
    self.assertIn("/dev/md0", self.formatted())

  def test_fill_partition_numbered_before_a_raid_member_is_formatted(self):
    # issue #273: the fill check read the loop's last partition (here the
    # RAID member numbered after it), so / was never formatted or put in fstab.
    self.build(disk("root", "/dev/sda",
                    {"partnum": 1, "mount": "/", "fill": True, "bootable": True},
                    {"partnum": 2, "mount": "raid", "size": 4096, "filesystem": "raid"}))
    self.assertEqual(self.installer.partDevices, {("root", 2): "/dev/sda3", ("root", 1): "/dev/sda4"})
    self.assertIn("/dev/sda4", self.formatted())
    self.assertNotIn("/dev/sda3", self.formatted())
    self.assertTrue(self.installer.rootpartUUID)

  def test_fill_raid_member_numbered_first_is_not_formatted(self):
    # and the other way round: a fill RAID member numbered before a normal
    # partition was formatted as if it were a filesystem.
    self.build(disk("root", "/dev/sda",
                    {"partnum": 1, "mount": "raid", "fill": True, "filesystem": "raid"},
                    {"partnum": 2, "mount": "/", "size": 8192, "bootable": True}))
    self.assertEqual(self.installer.partDevices, {("root", 2): "/dev/sda3", ("root", 1): "/dev/sda4"})
    self.assertNotIn("/dev/sda4", self.formatted())
    self.assertIn("/dev/sda3", self.formatted())

  def test_unknown_raid_member_stops_the_install(self):
    md = {"slug": "md0", "diskname": "/dev/md0", "dtype": "mdrd", "raidlevel": 1, "filesystem": "xfs", "mount": "/data", "partitions": [],
          "members": [{"disklayout": "root", "partnum": 9}]}
    with self.assertRaises(SystemExit):
      self.build(disk("root", "/dev/sda", {"partnum": 1, "mount": "/", "fill": True, "bootable": True}), md)


BY_ID = "/dev/disk/by-id/scsi-0QEMU_QEMU_HARDDISK_drive-scsi0"


def realpath(path):
  """ The rig's by-id link for scsi0 resolves to sda; everything else is already a kernel name. """
  return {BY_ID: "/dev/sda", "/dev/disk/by-id/nvme-disk": "/dev/nvme0n1"}.get(path, path)


class StatefulPartitionNameTests(StatefulInstallerTestCase):
  """ Issue #391: partitions are named the kernel's way, whatever the layout calls the disk. """

  def test_partition_names(self):
    for diskname, expected in (("/dev/sda", "/dev/sda3"), ("/dev/vda", "/dev/vda3"), ("/dev/nvme0n1", "/dev/nvme0n1p3"),
                               ("/dev/mmcblk0", "/dev/mmcblk0p3"), ("/dev/loop0", "/dev/loop0p3"), ("/dev/md127", "/dev/md127p3")):
      with self.subTest(diskname):
        self.assertEqual(self.installer._partName(diskname, 3), expected)

  @mock.patch("os.path.realpath", side_effect=realpath)
  def test_by_id_links_resolve_to_the_kernel_name(self, _):
    self.assertEqual(self.installer._partName(BY_ID, 1), "/dev/sda1")
    self.assertEqual(self.installer._partName("/dev/disk/by-id/nvme-disk", 1), "/dev/nvme0n1p1")

  @mock.patch("os.path.realpath", side_effect=realpath)
  def test_by_id_boot_disk(self, _):
    self.build(disk("root", BY_ID,
                    {"partnum": 1, "mount": "/", "fill": True, "bootable": True},
                    {"partnum": 2, "mount": "swap", "size": 1024, "filesystem": "linux-swap"}))
    # was BY_ID + "3" etc.
    self.assertEqual(self.installer.partDevices, {("root", 2): "/dev/sda3", ("root", 1): "/dev/sda4"})
    self.assertEqual(self.formatted(), ["/dev/sda2", "/dev/sda3", "/dev/sda4"])
    self.assertEqual(self.installer.bootpart, "/dev/sda1")
    self.assertIn("/dev/sda2\t/boot/efi\t\tvfat\tdefaults,noauto\t0 0", self.fstab_lines())
    # every layout partition is waited for before it's used, and the EFI one too.
    self.assertEqual([c.args[0] for c in self.wait.call_args_list], ["/dev/sda2", "/dev/sda3", "/dev/sda4"])

  @mock.patch("os.path.realpath", side_effect=realpath)
  def test_by_id_raid_member(self, _):
    md = {"slug": "md0", "diskname": "/dev/md0", "dtype": "mdrd", "raidlevel": 1, "filesystem": "xfs", "mount": "/data", "partitions": [],
          "members": [{"disklayout": "root", "partnum": 1}, {"disklayout": "second", "partnum": 1}]}
    self.build(disk("root", "/dev/sdb",
                    {"partnum": 1, "mount": "raid", "size": 4096, "filesystem": "raid"},
                    {"partnum": 2, "mount": "/", "fill": True, "bootable": True}),
               disk("second", BY_ID, {"partnum": 1, "mount": "raid", "size": 4096, "filesystem": "raid"}),
               md)
    create = [c.args[0] for c in self.sh.mdadm.call_args_list if "--create" in c.args[0]]
    self.assertEqual(create[0][-2:], ["/dev/sdb3", "/dev/sda1"])

  def test_nvme_boot_disk(self):
    self.build(disk("root", "/dev/nvme0n1", {"partnum": 1, "mount": "/", "fill": True, "bootable": True}))
    self.assertEqual(self.installer.partDevices, {("root", 1): "/dev/nvme0n1p3"})
    self.assertEqual(self.installer.bootpart, "/dev/nvme0n1p1")
    self.assertIn("/dev/nvme0n1p2\t/boot/efi\t\tvfat\tdefaults,noauto\t0 0", self.fstab_lines())


class StatefulPartitionWaitTests(StatefulInstallerTestCase):
  """ Issue #391: a new partition is waited for before mkfs/mkswap/mdadm use it. """

  def test_returns_once_the_device_exists(self):
    seen = iter([False, False, True])
    with mock.patch("os.path.exists", side_effect=lambda path: next(seen)), mock.patch.object(self.module.time, "sleep") as sleep:
      self.installer._waitForPartition("/dev/sda3")
    self.assertEqual(sleep.call_count, 2)

  def test_never_appearing_stops_the_install(self):
    clock = iter(range(0, 1000, 10))
    with mock.patch("os.path.exists", return_value=False), mock.patch.object(self.module.time, "sleep"), \
         mock.patch.object(self.module.time, "monotonic", side_effect=lambda: next(clock)):
      with self.assertRaises(SystemExit):
        self.installer._waitForPartition("/dev/sda3")


class StatefulMissingDiskTests(StatefulInstallerTestCase):
  """ Issue #391: a layout disk that doesn't exist stops the install before any disk is touched. """

  def run_installer(self, *layout, exists=()):
    self.installer.disklayout = list(layout)
    with mock.patch.object(self.installer, "_getDiskLayout"), \
         mock.patch("os.path.exists", side_effect=lambda path: path in exists), \
         mock.patch.object(self.module.time, "sleep"), \
         mock.patch("builtins.print") as self.print:
      self.installer.buildDisks()

  def printed(self):
    return "\n".join(" ".join(map(str, c.args)) for c in self.print.call_args_list)

  def test_by_id_disk_stops_before_anything_is_changed(self):
    with self.assertRaises(SystemExit):
      self.run_installer(disk("root", BY_ID, {"partnum": 1, "mount": "/", "fill": True, "bootable": True}))
    self.assertIn(f"disk {BY_ID} doesn't exist", self.printed())
    self.assertIn("use the kernel name", self.printed())
    self.sh.mdadm.assert_not_called()
    self.sh.mkfs.assert_not_called()

  def test_missing_kernel_name_has_no_by_id_hint(self):
    with self.assertRaises(SystemExit):
      self.run_installer(disk("root", "/dev/sda", {"partnum": 1, "mount": "/", "fill": True, "bootable": True}),
                         disk("data", "/dev/sdb", {"partnum": 1, "mount": "/data", "fill": True}), exists={"/dev/sda"})
    self.assertIn("disk /dev/sdb doesn't exist", self.printed())
    self.assertNotIn("/dev/sda doesn't exist", self.printed())
    self.assertNotIn("kernel name", self.printed())
    self.sh.mdadm.assert_not_called()

  def test_raid_devices_are_not_checked(self):
    md = {"slug": "md0", "diskname": "/dev/md0", "dtype": "mdrd", "raidlevel": 1, "filesystem": "xfs", "mount": "/data", "partitions": [],
          "members": [{"disklayout": "root", "partnum": 1}]}
    self.installer.disklayout = [disk("root", "/dev/sda", {"partnum": 1, "mount": "/", "fill": True, "bootable": True}), md]
    with mock.patch("os.path.exists", side_effect=lambda path: path == "/dev/sda"):
      self.installer._checkDisks()
