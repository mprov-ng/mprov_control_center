import importlib.util
import tempfile
from pathlib import Path
from unittest import mock

from django.conf import settings
from django.test import SimpleTestCase


def nic(name, mtu=1500):
  return {"name": name, "mtu": mtu, "network": None, "ipaddress": "10.0.0.5",
          "mac": "aa:bb:cc:dd:ee:ff", "isgateway": False}


class GenNetworkInterfacesMTUTests(SimpleTestCase):
  """ static/genNetworkInterfaces.py leaves the MTU of InfiniBand interfaces to the IB stack. """

  def setUp(self):
    path = Path(settings.BASE_DIR) / "static" / "genNetworkInterfaces.py"
    spec = importlib.util.spec_from_file_location("genNetworkInterfaces_under_test", path)
    self.module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(self.module)
    # skip __init__, which loads the node's config and talks to the mPCC.
    self.gen = self.module.mProvNetworkScriptGenerator.__new__(self.module.mProvNetworkScriptGenerator)
    self.tmp = tempfile.TemporaryDirectory()
    self.addCleanup(self.tmp.cleanup)
    self.gen.netscriptDir = self.tmp.name + "/"

  def generate(self, *nics):
    self.gen.details = {"hostname": "node01", "networkinterfaces": list(nics)}
    with mock.patch("builtins.open", self._open_outside_etc):
      self.gen.generateNetworkInterfaceFiles()

  def _open_outside_etc(self, file, *args, **kwargs):
    # /etc/hostname is written too; keep it in the temp dir.
    if file == "/etc/hostname":
      file = self.tmp.name + "/hostname"
    return self._real_open(file, *args, **kwargs)

  _real_open = open

  def ifcfg(self, name):
    return (Path(self.tmp.name) / f"ifcfg-{name}").read_text().splitlines()

  def test_infiniband_gets_no_mtu_even_with_a_stored_one(self):
    self.generate(nic("ib0", mtu=1500), nic("ib1", mtu=65520))
    for name in ("ib0", "ib1"):
      lines = self.ifcfg(name)
      self.assertIn("TYPE=InfiniBand", lines)
      self.assertFalse([l for l in lines if l.startswith("MTU=")], lines)

  def test_ethernet_keeps_its_mtu(self):
    self.generate(nic("ens18", mtu=9000), nic("eth0", mtu=None))
    self.assertIn("MTU=9000", self.ifcfg("ens18"))
    self.assertIn("MTU=1500", self.ifcfg("eth0"))
