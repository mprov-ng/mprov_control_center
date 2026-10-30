from unittest import mock

from systems.test_stateful_grub_cmdline import StatefulInstallerTestCase


class StatefulMountDisksTests(StatefulInstallerTestCase):
  """ Issue #275: mountDisks() makes no /newroot/none for swap entries. """

  def test_swap_gets_no_mount_point(self):
    fstab = "UUID=1\t/\t\txfs\tdefaults\t0 0\nUUID=2\tnone\t\tswap\tdefaults\t0 0\nUUID=3\t/scratch\t\txfs\tdefaults\t0 0\n"
    with mock.patch("builtins.open", mock.mock_open(read_data=fstab)), mock.patch.object(self.module.os, "makedirs") as makedirs:
      self.installer.mountDisks()
    made = [c.args[0] for c in makedirs.call_args_list]
    self.assertEqual(made, ["/newroot", "/newroot/", "/newroot/scratch"])
    self.assertEqual([c.args[0] for c in self.sh.mount.call_args_list], [["UUID=1", "/newroot/"], ["UUID=3", "/newroot/scratch"]])
