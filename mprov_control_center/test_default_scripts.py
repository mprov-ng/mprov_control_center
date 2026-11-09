import os
import re
import unittest

import yaml
from django.conf import settings
from django.test import SimpleTestCase

BUNDLE = os.path.join(settings.BASE_DIR, "default_scripts")
REF_FILE = os.path.join(settings.BASE_DIR, "install_scripts", "mprov_scripts.ref")


@unittest.skipUnless(os.path.isdir(BUNDLE), "default_scripts/ is built into the image only")
class DefaultScriptsBundleTests(SimpleTestCase):
  """ The image carries the default scripts from the mprov_scripts commit
  install_scripts/mprov_scripts.ref pins.  First start used to clone
  mprov_scripts master, so a released image's scripts changed from day to
  day (#460). """

  def test_bundle_is_the_pinned_commit(self):
    with open(REF_FILE) as f:
      ref = f.read().strip()
    with open(os.path.join(BUNDLE, ".ref")) as f:
      self.assertEqual(f.read().strip(), ref)

  def test_every_script_in_the_fixture_is_bundled(self):
    with open(os.path.join(BUNDLE, "mpcc_scripts.yaml")) as f:
      rows = yaml.safe_load(f)
    filenames = [row["fields"]["filename"] for row in rows if row.get("fields", {}).get("filename")]
    self.assertTrue(filenames)
    for name in filenames:
      self.assertTrue(os.path.isfile(os.path.join(BUNDLE, name)), name)

  def test_no_git_metadata(self):
    self.assertFalse(os.path.exists(os.path.join(BUNDLE, ".git")))

  def test_bundle_speaks_this_mpccs_version(self):
    """ The scripts send their version in mProv-Version, and the mPCC warns
    on every call when it isn't its own major.minor: 0.7.0 shipped default
    scripts that still said 0.6 (#544).  When the mPCC's minor version
    changes, the pin has to move to an mprov_scripts commit that speaks it. """
    from mprov_control_center.version import API_VERSION
    with open(os.path.join(BUNDLE, "VERSION")) as f:
      self.assertEqual(".".join(f.read().strip().split(".")[:2]), API_VERSION, "mprov_scripts VERSION")
    found = {}
    for root, _, files in os.walk(BUNDLE):
      for name in files:
        if not name.endswith((".py", ".sh")):
          continue
        path = os.path.join(root, name)
        with open(path, errors="replace") as f:
          for match in re.finditer(r"""^MPROV_SCRIPTS_VERSION\s*=\s*["']([^"']+)["']""", f.read(), re.M):
            found[os.path.relpath(path, BUNDLE)] = match.group(1)
    self.assertTrue(found, "no MPROV_SCRIPTS_VERSION in the bundled scripts")
    for path, version in found.items():
      self.assertEqual(".".join(version.split(".")[:2]), API_VERSION, path)
