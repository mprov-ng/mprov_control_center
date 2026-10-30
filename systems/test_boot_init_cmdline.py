import os
import re
import subprocess
import tempfile
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

SCRIPT = Path(settings.BASE_DIR) / "static" / "mprov_boot_init.sh"


class BootInitCmdlineTests(SimpleTestCase):
  """ static/mprov_boot_init.sh's get_kcmdline_opt matches the exact key and
  keeps the whole value (#285). """

  def setUp(self):
    function = re.search(r"^get_kcmdline_opt\(\)\{.*?^\}", SCRIPT.read_text(), re.S | re.M).group(0)
    self.cmdline = tempfile.NamedTemporaryFile("w", delete=False)
    self.addCleanup(os.unlink, self.cmdline.name)
    self.function = function.replace("/proc/cmdline", self.cmdline.name)

  def opt(self, cmdline, key):
    with open(self.cmdline.name, "w") as f:
      f.write(cmdline + "\n")
    result = subprocess.run(["bash", "-c", f'{self.function}\nget_kcmdline_opt "$1"', "bash", key],
                            capture_output=True, text=True, check=True)
    return result.stdout

  def test_the_value_of_the_key(self):
    cmdline = ("console=tty0 rdinit=/linuxrc mprov_image_url=http://10.0.0.1/images/compute "
               "mprov_initial_mods=e1000,tg3 mprov_tmpfs_size=8G mprov_stateful=1 mprov_prov_intf=bc:24:11:3b:cf:c8")
    self.assertEqual(self.opt(cmdline, "mprov_image_url"), "http://10.0.0.1/images/compute\n")
    self.assertEqual(self.opt(cmdline, "mprov_initial_mods"), "e1000,tg3\n")
    self.assertEqual(self.opt(cmdline, "mprov_stateful"), "1\n")

  def test_a_longer_key_doesnt_match(self):
    # was "1\n0\n": grep matched both.
    self.assertEqual(self.opt("mprov_stateful_disk=0 mprov_stateful=1", "mprov_stateful"), "1\n")
    self.assertEqual(self.opt("my_mprov_stateful=1", "mprov_stateful"), "\n")

  def test_a_value_with_an_equals_sign_is_kept_whole(self):
    # was "b": the part after the last '='.
    self.assertEqual(self.opt("mprov_image_url=http://h/images/compute?a=b", "mprov_image_url"),
                     "http://h/images/compute?a=b\n")

  def test_the_last_one_wins(self):
    self.assertEqual(self.opt("mprov_tmpfs_size=8G mprov_tmpfs_size=16G", "mprov_tmpfs_size"), "16G\n")

  def test_missing_key_is_empty(self):
    self.assertEqual(self.opt("console=tty0 quiet", "mprov_rescue"), "\n")


class BootInitImageDownloadTests(SimpleTestCase):
  """ static/mprov_boot_init.sh retries the image download when any stage of
  wget | gunzip | tar fails, not just tar (#286). """

  def setUp(self):
    text = SCRIPT.read_text()
    loop = re.search(r"^set -o pipefail\n.*?^set \+o pipefail\n", text, re.S | re.M).group(0)
    self.assertIn("wget", loop)
    # run the loop once: the retry's sleep stops the test shell instead.
    self.loop = loop.replace("cd /image || exit 1", "").replace("sleep 5", "exit 7")
    self.bin = tempfile.mkdtemp()

  def fake(self, name, status):
    with open(os.path.join(self.bin, name), "w") as f:
      f.write(f"#!/bin/bash\ncat > /dev/null\nexit {status}\n" if name != "wget" else f"#!/bin/bash\nexit {status}\n")
    os.chmod(os.path.join(self.bin, name), 0o755)

  def download(self, wget, gunzip, tar):
    self.fake("wget", wget)
    self.fake("gunzip", gunzip)
    self.fake("tar", tar)
    return subprocess.run(["bash", "-c", self.loop], capture_output=True, text=True,
                          env=dict(os.environ, PATH=f"{self.bin}:{os.environ['PATH']}", MPROV_IMAGE_URL="http://h/images/x"))

  def test_success(self):
    self.assertEqual(self.download(0, 0, 0).returncode, 0)

  def test_failed_wget_is_retried_even_when_tar_succeeds(self):
    result = self.download(1, 0, 0)
    self.assertEqual(result.returncode, 7)
    self.assertIn("Unable to retrieve image.  Retrying...", result.stdout)

  def test_failed_gunzip_is_retried_even_when_tar_succeeds(self):
    self.assertEqual(self.download(0, 1, 0).returncode, 7)

  def test_failed_tar_is_retried(self):
    self.assertEqual(self.download(0, 0, 2).returncode, 7)

  def test_pipefail_is_only_on_around_the_download(self):
    text = SCRIPT.read_text()
    self.assertLess(text.index("set -o pipefail"), text.index('if wget "$MPROV_IMAGE_URL"'))
    self.assertLess(text.index('if wget "$MPROV_IMAGE_URL"'), text.index("set +o pipefail"))
    self.assertEqual(text.count("set -o pipefail"), 1)
