import importlib.util
import os
from unittest import mock

from django.test import SimpleTestCase

import mprov_control_center.settings as live_settings


def load_settings(**environ):
  """ A fresh copy of settings.py, evaluated with these extra env vars. """
  spec = importlib.util.spec_from_file_location("settings_under_test", live_settings.__file__)
  module = importlib.util.module_from_spec(spec)
  with mock.patch.dict(os.environ, environ):
    spec.loader.exec_module(module)
  return module


class LdapLoggingTests(SimpleTestCase):
  """ #485: LDAP_ENABLED=1 used to replace LOGGING outright, to turn on
  django_auth_ldap's debug logging, which dropped the mPCC's own loggers
  (#433's provisioning lines, #170's nads lines) on every LDAP site. """

  def test_ldap_keeps_the_mprov_logger(self):
    settings = load_settings(LDAP_ENABLED="1")
    self.assertEqual(settings.LOGGING["loggers"]["mprov"], live_settings.LOGGING["loggers"]["mprov"])
    self.assertIn("mprov_stderr", settings.LOGGING["handlers"])

  def test_ldap_logs_warnings_by_default(self):
    settings = load_settings(LDAP_ENABLED="1")
    self.assertEqual(settings.LOGGING["loggers"]["django_auth_ldap"]["level"], "WARNING")

  def test_ldap_debug_turns_on_debug(self):
    settings = load_settings(LDAP_ENABLED="1", LDAP_DEBUG="1")
    self.assertEqual(settings.LOGGING["loggers"]["django_auth_ldap"]["level"], "DEBUG")

  def test_without_ldap_there_is_no_ldap_logger(self):
    settings = load_settings(LDAP_ENABLED="0")
    self.assertNotIn("django_auth_ldap", settings.LOGGING["loggers"])
