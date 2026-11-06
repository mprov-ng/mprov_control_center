import os
import re
import subprocess
import tempfile
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

STATIC = Path(settings.BASE_DIR) / "static"
SCRIPT = STATIC / "mprov_boot_init.sh"
BUNDLE = "/usr/libexec/mprov/bin/python3"


class BootInitImagePythonTests(SimpleTestCase):
  """ #476: static/mprov_boot_init.sh runs genNetworkInterfaces.py in the
  image on the job server's bundled python when the image has one (images
  built by mprov_jobserver 0.7.0 and later), else on /usr/bin/python3. """

  def setUp(self):
    text = SCRIPT.read_text()
    self.function = re.search(r"^image_python\(\) \{.*?^\}", text, re.S | re.M).group(0)
    self.root = tempfile.mkdtemp()
    self.bundle = os.path.join(self.root, BUNDLE.lstrip("/"))
    os.makedirs(os.path.dirname(self.bundle))

  def image_python(self):
    result = subprocess.run(["bash", "-c", f'{self.function}\nimage_python "$1"', "bash", self.root],
                            capture_output=True, text=True)
    self.assertEqual(result.returncode, 0, result.stderr)
    return result.stdout.strip()

  def test_an_image_without_the_bundle_uses_the_system_python(self):
    self.assertEqual(self.image_python(), "/usr/bin/python3")

  def test_an_image_with_the_bundle_uses_it(self):
    Path(self.bundle).write_text("#!/bin/sh\n")
    os.chmod(self.bundle, 0o755)
    self.assertEqual(self.image_python(), BUNDLE)

  def test_a_relative_symlink_to_the_bundles_python_counts(self):
    real = os.path.join(os.path.dirname(self.bundle), "python3.11")
    Path(real).write_text("#!/bin/sh\n")
    os.chmod(real, 0o755)
    os.symlink("python3.11", self.bundle)
    self.assertEqual(self.image_python(), BUNDLE)

  def test_an_absolute_symlink_counts_although_it_resolves_outside_the_image_here(self):
    # from the initramfs, /usr/libexec/mprov/... resolves against the initramfs
    # root, not the image's, so -x alone would miss it.
    os.symlink("/usr/libexec/mprov/python/bin/python3.11", self.bundle)
    self.assertEqual(self.image_python(), BUNDLE)

  def test_a_non_executable_file_isnt_used(self):
    Path(self.bundle).write_text("not a python\n")
    self.assertEqual(self.image_python(), "/usr/bin/python3")

  def test_gen_network_interfaces_runs_on_the_chosen_python(self):
    text = SCRIPT.read_text()
    self.assertIn('chroot /image/ "$(image_python /image)" /tmp/mprov_genNetworkInterfaces.py', text)


class NodeScriptsInterpreterTests(SimpleTestCase):
  """ #476: no node-side script served from static/ runs a Python script on
  a hardcoded /usr/bin/python3, which 0.7.0-built EL8 images don't have. """

  def test_no_hardcoded_system_python_for_the_node_scripts(self):
    for name in ("mprov_boot_init.sh", "mprov_stateful.sh"):
      with self.subTest(name):
        self.assertNotRegex((STATIC / name).read_text(), r"/usr/bin/python3\s+/tmp/")
