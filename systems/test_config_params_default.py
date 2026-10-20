from importlib import import_module

from django.apps import apps
from django.contrib.auth.models import User
from django.test import TestCase

from systems.models import System, SystemImage

migration = import_module('systems.migrations.0069_fix_config_params_default')


class ConfigParamsDefaultMigrationTests(TestCase):
  """ The data migration fixes the typo in rows still holding the old config_params default. """

  def setUp(self):
    self.user = User.objects.create(username="config-default-test")

  def test_new_rows_get_the_fixed_default(self):
    system = System.objects.create(hostname="new-node", created_by=self.user)
    self.assertEqual(system.config_params, migration.NEW_DEFAULT)

  def test_old_default_is_fixed_and_edited_values_are_left_alone(self):
    image = SystemImage.objects.create(name="old-image", created_by=self.user, config_params=migration.OLD_DEFAULT)
    old = System.objects.create(hostname="old-node", created_by=self.user, config_params=migration.OLD_DEFAULT)
    edited = migration.OLD_DEFAULT + "\nfoo: bar"
    custom = System.objects.create(hostname="custom-node", created_by=self.user, config_params=edited)

    migration.fix_config_params_default(apps, None)

    image.refresh_from_db()
    old.refresh_from_db()
    custom.refresh_from_db()
    self.assertEqual(image.config_params, migration.NEW_DEFAULT)
    self.assertEqual(old.config_params, migration.NEW_DEFAULT)
    self.assertEqual(custom.config_params, edited)
