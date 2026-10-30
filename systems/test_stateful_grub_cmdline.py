import importlib.util
import sys
from pathlib import Path
from unittest import mock

from django.conf import settings
from django.test import SimpleTestCase


class StatefulInstallerTestCase(SimpleTestCase):
  """ Loads static/mprov_stateful.py with fake parted and sh. """

  def setUp(self):
    path = Path(settings.BASE_DIR) / "static" / "mprov_stateful.py"
    spec = importlib.util.spec_from_file_location("mprov_stateful_under_test", path)
    self.module = importlib.util.module_from_spec(spec)
    self.sh = mock.MagicMock()
    with mock.patch.dict(sys.modules, {"parted": mock.MagicMock(), "sh": self.sh}):
      spec.loader.exec_module(self.module)
    # skip __init__, which loads the node's config.
    self.installer = self.module.mProvStatefulInstaller.__new__(self.module.mProvStatefulInstaller)
    self.installer.modules = ""


class StatefulGrubCmdlineTests(StatefulInstallerTestCase):
  """ Issue #276: the installed system's GRUB_CMDLINE_LINUX keeps arguments without '='. """

  CMDLINE = ("initrd=initramfs BOOT_IMAGE=vmlinuz quiet ro rhgb console=ttyS0,115200 rdinit=/init "
             "mprov_stateful=1 mprov_rescue mprov_initial_mods=tg3,ixgbe autorelabel=1 crashkernel=auto\n")

  def test_bare_arguments_are_kept(self):
    self.assertEqual(self.installer._grubCmdline(self.CMDLINE),
                     ["BOOT_IMAGE=vmlinuz", "quiet", "ro", "rhgb", "console=ttyS0,115200", "crashkernel=auto"])

  def test_initial_mods_are_noted(self):
    self.installer._grubCmdline(self.CMDLINE)
    self.assertEqual(self.installer.modules, "tg3 ixgbe")

  def test_whitespace_and_the_trailing_newline_are_dropped(self):
    self.assertEqual(self.installer._grubCmdline("quiet  ro\n"), ["quiet", "ro"])

