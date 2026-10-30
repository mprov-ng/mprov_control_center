import importlib.util
import tempfile
from pathlib import Path
from unittest import mock

from django.conf import settings
from django.test import SimpleTestCase


def nic(name, mtu=1500):
  return {"name": name, "mtu": mtu, "network": None, "ipaddress": "10.0.0.5",
          "mac": "aa:bb:cc:dd:ee:ff", "isgateway": False}


class GenNetworkInterfacesTestCase(SimpleTestCase):
  """ Loads static/genNetworkInterfaces.py and writes its ifcfg files to a temp dir. """

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


class GenNetworkInterfacesMTUTests(GenNetworkInterfacesTestCase):
  """ static/genNetworkInterfaces.py leaves the MTU of InfiniBand interfaces to the IB stack. """

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


def reply(status, body=None):
  return mock.Mock(status_code=status, **{"json.return_value": body})


class GenNetworkInterfacesTests(GenNetworkInterfacesTestCase):
  """ Issues #280-#284 in static/genNetworkInterfaces.py. """

  def config(self, url):
    path = Path(self.tmp.name) / "script-runner.yaml"
    path.write_text(f"- global:\n    mprovURL: '{url}'\n    apikey: 'key'\n")
    self.gen.configfile = str(path)
    self.gen.load_config()

  def test_mprov_url_gets_exactly_one_trailing_slash(self):
    for url in ("http://mpcc", "http://mpcc/", "http://mpcc//"):
      with self.subTest(url):
        self.config(url)
        self.assertEqual(self.gen.mprovURL, "http://mpcc/")

  def test_every_request_has_a_single_slash(self):
    self.config("http://mpcc")
    self.gen.session = mock.Mock()
    self.gen.session.get.side_effect = [reply(200, [{"id": 7, "hostname": "node01"}]),
                                        reply(200, [{**nic("ens18"), "network": 3}]),
                                        reply(200, {"gateway": "", "netmask": 24, "subnet": "10.1.0.0"})]
    self.gen._getSelf()
    with mock.patch("builtins.open", self._open_outside_etc):
      self.gen.generateNetworkInterfaceFiles()
    self.assertEqual([c.args[0] for c in self.gen.session.get.call_args_list],
                     ["http://mpcc/systems/?self", "http://mpcc/networkinterfaces/?system=7", "http://mpcc/networks/3/"])
    self.assertIn("NETMASK=255.255.255.0", self.ifcfg("ens18"))

  def test_unreachable_mpcc_is_reported_not_a_crash(self):
    self.gen.apikey = "key"
    self.gen.session = mock.Mock(headers={})
    self.gen.session.get.side_effect = self.module.requests.exceptions.ConnectionError("connection refused")
    with mock.patch.object(self.module.time, "sleep"), mock.patch("sys.stderr") as stderr:
      self.assertFalse(self.gen.startSession())
    self.assertIn("connection refused", "".join(c.args[0] for c in stderr.write.call_args_list))

  def test_network_without_a_netmask_gets_the_default(self):
    self.gen.mprovURL = "http://mpcc/"
    self.gen.session = mock.Mock()
    self.gen.session.get.return_value = reply(200, {"gateway": "10.0.0.1", "netmask": None, "subnet": "10.0.0.0"})
    self.generate({**nic("ens18"), "network": 3})
    self.assertIn("NETMASK=255.0.0.0", self.ifcfg("ens18"))

  def test_netscript_dir_gets_one_trailing_slash(self):
    for configured, expected in (("/etc/sysconfig/network-scripts", "/etc/sysconfig/network-scripts/"),
                                 ("/etc/sysconfig/network-scripts/", "/etc/sysconfig/network-scripts/")):
      with self.subTest(configured), \
           mock.patch.object(self.module.mProvNetworkScriptGenerator, "load_config"), \
           mock.patch.object(self.module.mProvNetworkScriptGenerator, "startSession", return_value=True), \
           mock.patch.object(self.module.mProvNetworkScriptGenerator, "_getSelf"), \
           mock.patch.object(self.module.mProvNetworkScriptGenerator, "netscriptDir", configured):
        self.assertEqual(self.module.mProvNetworkScriptGenerator().netscriptDir, expected)

  def test_shebang(self):
    path = Path(settings.BASE_DIR) / "static" / "genNetworkInterfaces.py"
    self.assertEqual(path.read_text().splitlines()[0], "#!/usr/bin/env python3")
