import importlib.util
import json
import os
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from django.conf import settings
from django.test import SimpleTestCase


def reply(status, body=None):
  return SimpleNamespace(status_code=status, text=json.dumps(body), json=lambda: body)


class StatefulNetbootTests(SimpleTestCase):
  """ Issues #323 and #278: the installer only finishes once the mPCC has cleared provision. """

  def setUp(self):
    path = Path(settings.BASE_DIR) / "static" / "mprov_stateful.py"
    spec = importlib.util.spec_from_file_location("mprov_stateful_under_test", path)
    self.module = importlib.util.module_from_spec(spec)
    with mock.patch.dict(sys.modules, {"parted": mock.MagicMock(), "sh": mock.MagicMock()}):
      spec.loader.exec_module(self.module)
    # skip __init__, which loads the node's config.
    self.installer = self.module.mProvStatefulInstaller.__new__(self.module.mProvStatefulInstaller)
    self.installer.mprovURL = "http://mpcc:8080/"
    self.installer.session = mock.Mock()
    patcher = mock.patch.object(self.module.time, "sleep")
    self.sleep = patcher.start()
    self.addCleanup(patcher.stop)

  def test_confirmed_on_the_first_try(self):
    self.installer.session.post.return_value = reply(200, {"provision": False, "bootable_nic": "ens18"})
    self.installer.disableNetboot()
    # one slash, through the session (its headers carry the API key).
    self.installer.session.post.assert_called_once_with("http://mpcc:8080/systems/?self", data='{"netboot": false}', timeout=(10, 30))
    self.sleep.assert_not_called()

  def test_server_errors_and_connection_errors_are_retried(self):
    self.installer.session.post.side_effect = [Exception("connection refused"), reply(502), reply(200, {"provision": False})]
    self.installer.disableNetboot()
    self.assertEqual(self.installer.session.post.call_count, 3)
    self.assertEqual([c.args[0] for c in self.sleep.call_args_list], [2, 4])

  def test_a_hung_mpcc_times_out_and_is_retried(self):
    timeout = self.module.requests.exceptions.ReadTimeout("Read timed out. (read timeout=30)")
    self.installer.session.post.side_effect = [timeout, timeout, reply(200, {"provision": False})]
    self.installer.disableNetboot()
    self.assertEqual(self.installer.session.post.call_count, 3)
    for call in self.installer.session.post.call_args_list:
      self.assertEqual(call.kwargs["timeout"], (10, 30))

  def test_never_confirmed_stops_the_install(self):
    self.installer.session.post.side_effect = Exception("no route to host")
    with self.assertRaises(SystemExit) as stop:
      self.installer.disableNetboot()
    self.assertEqual(stop.exception.code, 1)
    self.assertEqual(self.installer.session.post.call_count, 5)

  def test_a_client_error_stops_at_once(self):
    # e.g. 404: no NIC has this node's address.  Retrying won't fix that.
    self.installer.session.post.return_value = reply(404, {"detail": "No network interface has the IP address 10.0.0.9."})
    with self.assertRaises(SystemExit):
      self.installer.disableNetboot()
    self.installer.session.post.assert_called_once()

  def test_provision_still_set_is_not_success(self):
    self.installer.session.post.return_value = reply(200, {"provision": True})
    with self.assertRaises(SystemExit):
      self.installer.disableNetboot()

  def test_cleanup_disables_netboot(self):
    with mock.patch.object(self.installer, "disableNetboot") as disable:
      self.installer.cleanupAndSwitchroot()
    disable.assert_called_once_with()

  def test_mprov_url_gets_exactly_one_trailing_slash(self):
    for url in ("http://mpcc:8080", "http://mpcc:8080/", "http://mpcc:8080//"):
      with self.subTest(url), tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as config:
        config.write(f"- global:\n    mprovURL: '{url}'\n    apikey: x\n")
      self.addCleanup(os.unlink, config.name)
      self.installer.configfile = config.name
      self.installer.load_config()
      self.assertEqual(self.installer.mprovURL, "http://mpcc:8080/")
