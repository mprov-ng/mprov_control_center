import importlib.util
import sys
import types
from pathlib import Path
from unittest import mock

from django.conf import settings
from django.test import SimpleTestCase


class FakePartition:
  def __init__(self, **kwargs):
    self.flags = []

  def setFlag(self, flag):
    self.flags.append(flag)


def fake_parted():
  """ Just enough of pyparted for _createPartition(), with the flag numbers of the node images' libparted. """
  parted = types.ModuleType("parted")
  parted.PARTITION_NORMAL = 0
  parted.PARTITION_SWAP = 3
  parted.PARTITION_RAID = 5
  parted.PARTITION_BIOS_GRUB = 12
  parted.partitionFlag = {1: 'boot', 3: 'swap', 5: 'raid', 12: 'bios_grub', 18: 'esp'}
  parted.Geometry = mock.Mock
  parted.FileSystem = mock.Mock
  parted.Partition = FakePartition
  return parted


class StatefulPartitionTypeTests(SimpleTestCase):
  """ static/mprov_stateful.py flags each partition by what it holds, so only the EFI partition gets the ESP type. """

  def setUp(self):
    path = Path(settings.BASE_DIR) / "static" / "mprov_stateful.py"
    spec = importlib.util.spec_from_file_location("mprov_stateful_under_test", path)
    module = importlib.util.module_from_spec(spec)
    with mock.patch.dict(sys.modules, {"parted": fake_parted(), "sh": mock.MagicMock()}):
      spec.loader.exec_module(module)
    # skip __init__, which loads the node's config.
    self.installer = module.mProvStatefulInstaller.__new__(module.mProvStatefulInstaller)
    self.installer.bootdisk = "/dev/sda"
    self.disk = mock.Mock()
    self.device = mock.Mock(path="/dev/sda", **{"getLength.return_value": 67108864})

  def flags(self, filesystem, **part):
    self.disk.addPartition.reset_mock()
    part = {"filesystem": filesystem, "size": 100, "fill": False, "partnum": 3, "mount": "/", **part}
    self.installer._createPartition(self.device, self.disk, part, 512, 2048)
    return self.disk.addPartition.call_args.kwargs["partition"].flags

  def test_efi_partition_is_the_esp(self):
    self.assertEqual(self.flags("efi"), [18])

  def test_filesystems_keep_the_default_type(self):
    for filesystem in ("xfs", "ext4"):
      with self.subTest(filesystem):
        self.assertEqual(self.flags(filesystem), [])
    self.assertEqual(self.flags("xfs", fill=True), [])

  def test_raid_and_swap_get_their_own_types(self):
    self.assertEqual(self.flags("raid", mount="raid"), [5])
    self.assertEqual(self.flags("linux-swap", mount="swap"), [3])

  def test_biosboot_gets_only_bios_grub(self):
    self.assertEqual(self.flags("biosboot"), [12])
