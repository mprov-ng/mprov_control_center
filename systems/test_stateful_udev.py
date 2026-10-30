import os
import subprocess
import tempfile
from pathlib import Path
from unittest import mock

from django.conf import settings
from django.test import SimpleTestCase

from systems.test_stateful_partition_devices import BY_ID, StatefulInstallerTestCase, disk, realpath

SCRIPT = Path(settings.BASE_DIR) / "static" / "mprov_stateful.sh"


class StatefulUdevScriptTests(SimpleTestCase):
  """ Issue #410: static/mprov_stateful.sh runs the image's udev around the
  installer, for block devices only, with the md/LVM assembly rules masked. """

  def setUp(self):
    self.tmp = tempfile.mkdtemp()
    self.log = os.path.join(self.tmp, "log")
    self.rules = os.path.join(self.tmp, "rules.d")
    self.bin = os.path.join(self.tmp, "bin")
    os.mkdir(self.bin)
    for name in ("udevadm", "pkill"):
      self.fake(name, 0)

  def fake(self, name, status):
    path = os.path.join(self.bin, name)
    with open(path, "w") as f:
      f.write(f'#!/bin/bash\necho "{name} $*" >> {self.log}\nexit {status}\n')
    os.chmod(path, 0o755)
    return path

  def run_script(self, udevd=0, installer=0, has_udevd=True):
    udevd_path = self.fake("systemd-udevd", udevd) if has_udevd else os.path.join(self.bin, "no-such-udevd")
    text = SCRIPT.read_text() \
      .replace("/usr/lib/systemd/systemd-udevd", udevd_path) \
      .replace("/run/udev/rules.d", self.rules) \
      .replace("/usr/bin/python3 /tmp/mprov_stateful.py", self.fake("python3", installer))
    result = subprocess.run(["bash", "-c", text], capture_output=True, text=True,
                            env=dict(os.environ, PATH=f"{self.bin}:{os.environ['PATH']}"))
    calls = Path(self.log).read_text().splitlines() if os.path.exists(self.log) else []
    return result, calls

  def test_udev_runs_around_the_installer(self):
    result, calls = self.run_script()
    self.assertEqual(result.returncode, 0, result.stderr)
    self.assertEqual(calls, [
      "systemd-udevd --daemon",
      "udevadm trigger --action=add --subsystem-match=block",
      "udevadm settle --timeout=30",
      "python3 ",
      "udevadm control --exit",
    ])

  def test_md_and_lvm_assembly_rules_are_masked(self):
    self.run_script()
    for rule in ("64-md-raid-assembly.rules", "65-md-incremental.rules", "69-dm-lvm-metad.rules", "69-dm-lvm.rules"):
      self.assertEqual(Path(self.rules, rule).read_text(), "", rule)

  def test_udev_is_stopped_when_the_installer_fails(self):
    result, calls = self.run_script(installer=1)
    self.assertEqual(result.returncode, 1)
    self.assertEqual(calls[-2:], ["python3 ", "udevadm control --exit"])

  def test_udevd_is_killed_if_it_wont_exit(self):
    self.fake("udevadm", 1)
    result, calls = self.run_script()
    self.assertEqual(result.returncode, 0)
    self.assertEqual(calls[-2:], ["udevadm control --exit", f"pkill -f {self.bin}/systemd-udevd"])

  def test_install_goes_on_without_udev(self):
    for kwargs in ({"has_udevd": False}, {"udevd": 1}):
      with self.subTest(**kwargs):
        if os.path.exists(self.log):
          os.unlink(self.log)
        result, calls = self.run_script(**kwargs)
        self.assertEqual(result.returncode, 0)
        self.assertIn("disk layouts must use kernel disk names", result.stdout)
        self.assertNotIn("udevadm trigger --action=add --subsystem-match=block", calls)
        self.assertNotIn("udevadm control --exit", calls)
        self.assertIn("python3 ", calls)


class StatefulUdevInstallerTests(StatefulInstallerTestCase):
  """ Issue #410: static/mprov_stateful.py with a /dev/disk/ link as the boot disk. """

  @mock.patch("os.path.realpath", side_effect=realpath)
  def test_by_id_boot_disk_matches_parteds_kernel_name(self, _):
    # libparted names the device by its resolved path, not the link.
    self.module.parted.getDevice = lambda path: mock.Mock(path=realpath(path), sectorSize=512,
                                                          **{"getLength.return_value": 67108864})
    self.build(disk("root", BY_ID, {"partnum": 1, "mount": "/", "fill": True, "bootable": True}))
    self.assertEqual(self.installer.bootpart, "/dev/sda1")
    self.assertEqual(self.installer.partDevices, {("root", 1): "/dev/sda3"})

  @mock.patch("os.path.realpath", side_effect=realpath)
  def test_grub_is_installed_on_the_kernel_name(self, _):
    self.installer.bootdisk = BY_ID
    self.installer.modules = ""
    self.installer.rootpartUUID = "UUID=abc"
    with mock.patch("os.path.exists", return_value=False), \
         mock.patch("builtins.open", mock.mock_open(read_data="console=tty0\n")), \
         mock.patch.object(self.installer, "realModules", return_value=[]), \
         mock.patch("builtins.print"):
      self.installer.installBootLoader()
    grub = [c.args[0] for c in self.sh.chroot.call_args_list if "grub2-install" in c.args[0]]
    self.assertEqual(len(grub), 1)
    self.assertEqual(grub[0][-1], "/dev/sda")

  def test_new_partitions_are_settled_then_waited_for(self):
    with mock.patch("os.path.exists", return_value=True):
      self.installer._waitForPartition("/dev/sda3")
    self.sh.udevadm.assert_called_once_with(["settle", "--timeout=30"])

  def test_a_failed_settle_only_warns(self):
    self.sh.udevadm.side_effect = Exception("no udevd running")
    with mock.patch("os.path.exists", return_value=True), mock.patch("builtins.print") as printed:
      self.installer._waitForPartition("/dev/sda3")
    self.assertIn("udevadm settle failed", printed.call_args.args[0])
