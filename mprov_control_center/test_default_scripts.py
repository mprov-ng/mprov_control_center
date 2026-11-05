import os
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
