import os
import re
import subprocess
import tempfile
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

SCRIPT = Path(settings.BASE_DIR) / "static" / "mprov_boot_init.sh"


class BootInitRespawnTests(SimpleTestCase):
  """ #533: once this boot's one-time enrollment nonce may have been used,
  the console's 'r' reboots for a new one instead of restarting the boot,
  which would send the same nonce again. """

  def setUp(self):
    text = SCRIPT.read_text()
    functions = "\n".join(re.search(rf"^{name}\(\) \{{.*?^\}}", text, re.S | re.M).group(0)
                          for name in ("reboot_node", "respawn"))
    self.tmp = tempfile.TemporaryDirectory()
    self.addCleanup(self.tmp.cleanup)
    self.root = self.tmp.name
    os.makedirs(f"{self.root}/image/tmp")
    os.makedirs(f"{self.root}/tmp")
    self.sysrq = f"{self.root}/sysrq-trigger"
    functions = (functions.replace("/proc/sysrq-trigger", self.sysrq)
                 .replace("/bin/busybox reboot -f", "echo BUSYBOX-REBOOT")
                 .replace('"/image$ENROLL_SPENT"', f'"{self.root}/image/tmp/mprov_enroll_spent"'))
    stubs = ("mount() { :; }\numount() { echo UMOUNT; }\nsync() { :; }\n"
             "sleep() { if [ \"$1\" = 3600 ]; then echo HUNG; exit 7; fi; }\n")
    self.script = f"ENROLL_SPENT={self.root}/tmp/mprov_enroll_spent\n{stubs}{functions}\nrespawn\n"

  def press(self, keys):
    return subprocess.run(["bash", "-c", self.script], input=keys, capture_output=True, text=True, timeout=10)

  def test_restarts_when_nothing_was_enrolled(self):
    result = self.press("r")
    self.assertEqual(result.returncode, 0)
    self.assertIn("Press 'r' to restart the mProv Boot System.", result.stdout)
    self.assertIn("Restarting...", result.stdout)
    self.assertFalse(os.path.exists(self.sysrq))

  def test_reboots_once_the_nonce_was_used(self):
    for marker in ("tmp", "image/tmp"):
      with self.subTest(marker=marker):
        for stale in ("tmp", "image/tmp"):
          Path(f"{self.root}/{stale}/mprov_enroll_spent").unlink(missing_ok=True)
        Path(f"{self.root}/{marker}/mprov_enroll_spent").touch()
        result = self.press("xr")
        self.assertIn("one-time enrollment nonce has been used", result.stdout)
        self.assertIn("Press 'r' to reboot this node for a new one.", result.stdout)
        self.assertNotIn("Restarting...", result.stdout)
        self.assertEqual(Path(self.sysrq).read_text(), "b\n")
        self.assertIn("BUSYBOX-REBOOT", result.stdout)
        # never returns to init, which would run the boot again
        self.assertIn("unable to reboot", result.stdout)
        self.assertEqual(result.returncode, 7)

  def test_the_note_is_kept_where_a_restart_doesnt_clear_it(self):
    text = SCRIPT.read_text()
    run = text.index('/tmp/mprov_genNetworkInterfaces.py\n')
    keep = text.index('touch "$ENROLL_SPENT"')
    self.assertLess(run, keep)
    self.assertLess(text.index("ENROLL_SPENT=/tmp/mprov_enroll_spent"), text.index("respawn() {"))
