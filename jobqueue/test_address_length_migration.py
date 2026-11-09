from unittest import skipUnless

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class AddressLengthMigrationTests(TransactionTestCase):
  """ 0021 shrinks JobServerAddress.address to 255 (#527): short addresses are
  kept, any longer one is dropped first. """

  migrate_from = [("jobqueue", "0020_job_last_update_auto_now")]
  migrate_to = [("jobqueue", "0021_jobserveraddress_address_255")]

  def setUp(self):
    executor = MigrationExecutor(connection)
    executor.migrate(self.migrate_from)
    apps = executor.loader.project_state(self.migrate_from).apps
    server = apps.get_model("jobqueue", "JobServer").objects.create(name="js1", address="10.0.0.1")
    self.Address = apps.get_model("jobqueue", "JobServerAddress")
    self.short = self.Address.objects.create(jobserver=server, address="fe80::1%eth0").pk
    self.edge = self.Address.objects.create(jobserver=server, address="h" * 255).pk

  def tearDown(self):
    executor = MigrationExecutor(connection)
    executor.loader.build_graph()
    executor.migrate(executor.loader.graph.leaf_nodes())

  def migrate(self):
    executor = MigrationExecutor(connection)
    executor.loader.build_graph()
    executor.migrate(self.migrate_to)
    return executor.loader.project_state(self.migrate_to).apps.get_model("jobqueue", "JobServerAddress")

  def test_short_addresses_are_kept(self):
    Address = self.migrate()
    self.assertEqual(set(Address.objects.values_list("pk", flat=True)), {self.short, self.edge})
    self.assertEqual(Address._meta.get_field("address").max_length, 255)

  # Only SQLite can hold an over-long value here: the test database's column
  # is created at 255 by the current 0016, and MariaDB/MySQL enforce that.
  @skipUnless(connection.vendor == "sqlite", "needs a database that doesn't enforce varchar length")
  def test_an_over_long_address_is_dropped(self):
    long = self.Address.objects.create(jobserver_id=self.Address.objects.get(pk=self.short).jobserver_id,
                                       address="x" * 300).pk
    Address = self.migrate()
    self.assertFalse(Address.objects.filter(pk=long).exists())
    self.assertTrue(Address.objects.filter(pk=self.short).exists())
