import importlib.util
import sys
import tempfile
from pathlib import Path
from unittest import mock

from django.conf import settings
from django.test import SimpleTestCase


class StatefulCABundleTests(SimpleTestCase):
  """ static/mprov_stateful.py checks an https mprovURL against the CA its
  config names (the global caBundle setting). """

  def setUp(self):
    path = Path(settings.BASE_DIR) / "static" / "mprov_stateful.py"
    spec = importlib.util.spec_from_file_location("mprov_stateful_ca_under_test", path)
    self.module = importlib.util.module_from_spec(spec)
    with mock.patch.dict(sys.modules, {"parted": mock.MagicMock(), "sh": mock.MagicMock()}):
      spec.loader.exec_module(self.module)
    self.installer = self.module.mProvStatefulInstaller.__new__(self.module.mProvStatefulInstaller)
    self.tmp = tempfile.TemporaryDirectory()
    self.addCleanup(self.tmp.cleanup)

  def start(self, config):
    path = Path(self.tmp.name) / "script-runner.yaml"
    path.write_text(config)
    self.installer.configfile = str(path)
    self.installer.load_config()
    self.installer.session = mock.Mock(headers={})
    self.installer.session.get.return_value = mock.Mock(status_code=200, raw=mock.Mock(fileno=mock.Mock(return_value=0)))
    with mock.patch.object(self.module, "mprov_enroll", None), mock.patch.object(self.module.socket, "fromfd"):
      self.assertTrue(self.installer.startSession())

  def test_ca_bundle_is_used_for_the_session(self):
    self.start("- global:\n    mprovURL: 'https://mpcc/'\n    apikey: 'key'\n    caBundle: '/etc/mprov/mpcc-ca.crt'\n")
    self.assertEqual(self.installer.session.verify, "/etc/mprov/mpcc-ca.crt")

  def test_without_one_the_session_is_left_alone(self):
    self.start("- global:\n    mprovURL: 'http://mpcc/'\n    apikey: 'key'\n")
    self.assertNotEqual(self.installer.session.verify, "/etc/mprov/mpcc-ca.crt")
