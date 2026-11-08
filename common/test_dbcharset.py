""" Tests for common/dbcharset.py: converting tables an older release left in
another collation before migrations run (#526). """
import io
import unittest
from unittest import mock

from django.core.management.sql import emit_pre_migrate_signal
from django.db import connection, connections
from django.test import SimpleTestCase

from common import dbcharset

MYSQL = connection.vendor == "mysql"


class HookTests(SimpleTestCase):
    def test_runs_once_before_migrations(self):
        with mock.patch.object(dbcharset, "normalize") as normalize:
            emit_pre_migrate_signal(verbosity=0, interactive=False, db="default")
        normalize.assert_called_once()
        self.assertIs(normalize.call_args.args[0], connections["default"])

    @unittest.skipIf(MYSQL, "the no-op is for other databases")
    def test_noop_on_other_databases(self):
        self.assertEqual(dbcharset.normalize(connection, verbosity=0), 0)


@unittest.skipUnless(MYSQL, "MySQL/MariaDB only")
class NormalizeTests(SimpleTestCase):
    """ Old tables are made by hand in latin1, as a database first created by
    an older release has them, next to Django's own tables in the test
    database's utf8mb4. """
    databases = {"default"}
    TABLES = ["t526_cred", "t526_sys", "t526_m2m", "t526_img", "t526_names", "t526_addr", "t526_js"]

    def sql(self, *statements):
        with connection.cursor() as cursor:
            for s in statements:
                cursor.execute(s)
            try:
                return cursor.fetchall()
            except Exception:
                return None

    def setUp(self):
        self.drop()
        self.addCleanup(self.drop)
        with connection.cursor() as cursor:
            self.collation = dbcharset.target_collation(cursor)
        self.sql(
            # meta is what MariaDB makes of a JSONField: utf8mb4_bin, checked
            "CREATE TABLE t526_img (slug varchar(50) NOT NULL PRIMARY KEY, name varchar(255) NOT NULL, "
            "meta longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL CHECK (json_valid(meta))) "
            "ENGINE=InnoDB DEFAULT CHARSET=latin1 COLLATE=latin1_swedish_ci ROW_FORMAT=COMPACT",
            "CREATE TABLE t526_sys (id int AUTO_INCREMENT PRIMARY KEY, image_id varchar(50) NULL, "
            "hostname varchar(255) NOT NULL UNIQUE, "
            "CONSTRAINT t526_sys_img FOREIGN KEY (image_id) REFERENCES t526_img (slug)) "
            "ENGINE=InnoDB DEFAULT CHARSET=latin1 COLLATE=latin1_swedish_ci ROW_FORMAT=COMPACT",
            "CREATE TABLE t526_m2m (id int AUTO_INCREMENT PRIMARY KEY, img_id varchar(50) NOT NULL, "
            "sys_id int NOT NULL, "
            "CONSTRAINT t526_m2m_img FOREIGN KEY (img_id) REFERENCES t526_img (slug) ON DELETE CASCADE, "
            "CONSTRAINT t526_m2m_sys FOREIGN KEY (sys_id) REFERENCES t526_sys (id)) "
            "ENGINE=InnoDB DEFAULT CHARSET=latin1 COLLATE=latin1_swedish_ci",
            "INSERT INTO t526_img VALUES ('compute', _latin1 X'636166E9', '{}')",
            "INSERT INTO t526_sys (image_id, hostname) VALUES ('compute', 'n1')",
            "INSERT INTO t526_m2m (img_id, sys_id) VALUES ('compute', 1)",
        )

    def drop(self):
        self.sql("SET SESSION foreign_key_checks = 0",
                 *["DROP TABLE IF EXISTS %s" % t for t in self.TABLES + [dbcharset.BACKUP_TABLE]],
                 "SET SESSION foreign_key_checks = 1")

    def collations(self):
        return dict(self.sql("SELECT TABLE_NAME, TABLE_COLLATION FROM information_schema.TABLES "
                             "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME LIKE 't526\\_%'"))

    def keys(self):
        return sorted(self.sql(
            "SELECT CONSTRAINT_NAME, TABLE_NAME, REFERENCED_TABLE_NAME, DELETE_RULE "
            "FROM information_schema.REFERENTIAL_CONSTRAINTS "
            "WHERE CONSTRAINT_SCHEMA = DATABASE() AND TABLE_NAME LIKE 't526\\_%'"))

    def new_foreign_key(self):
        # what a new migration does: a table in the default collation with a
        # foreign key to the old string key
        self.sql("CREATE TABLE t526_cred (id int AUTO_INCREMENT PRIMARY KEY, image_id varchar(50) NULL, "
                 "CONSTRAINT t526_cred_img FOREIGN KEY (image_id) REFERENCES t526_img (slug)) ENGINE=InnoDB")

    def test_nothing_to_do_on_a_migrated_database(self):
        # Django's own tables, as this release makes them (JSON columns in
        # utf8mb4_bin included), need nothing
        self.drop()
        self.assertEqual(dbcharset.normalize(connection, verbosity=0), 0)

    def test_new_foreign_key_fails_before(self):
        # errno 150 on MariaDB, 3780 on MySQL
        from django.db import DatabaseError
        with self.assertRaises(DatabaseError):
            self.new_foreign_key()

    def test_converts_and_keeps_foreign_keys(self):
        keys = self.keys()
        out = io.StringIO()
        self.assertEqual(dbcharset.normalize(connection, stdout=out), 3)
        self.assertIn("Converting 3 tables to %s" % self.collation, out.getvalue())
        self.assertEqual(set(self.collations().values()), {self.collation})
        self.assertEqual(self.keys(), keys)
        # the data came across as text, not bytes
        self.assertEqual(self.sql("SELECT name FROM t526_img"), (("café",),))
        # the foreign keys still hold
        from django.db import IntegrityError
        with self.assertRaises(IntegrityError):
            self.sql("INSERT INTO t526_sys (image_id, hostname) VALUES ('nope', 'n2')")
        self.sql("DELETE FROM t526_m2m")
        # the long unique key fits: the COMPACT table became DYNAMIC
        self.assertEqual(self.sql("SELECT ROW_FORMAT FROM information_schema.TABLES "
                                  "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 't526_sys'"), (("Dynamic",),))
        self.new_foreign_key()
        self.assertFalse(self.sql("SHOW TABLES LIKE '%s'" % dbcharset.BACKUP_TABLE))
        # the JSON column kept its binary collation and its check
        self.assertEqual(self.sql("SELECT COLLATION_NAME FROM information_schema.COLUMNS WHERE "
                                  "TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 't526_img' AND COLUMN_NAME = 'meta'"),
                         (("utf8mb4_bin",),))
        from django.db import DatabaseError
        with self.assertRaises(DatabaseError):
            self.sql("INSERT INTO t526_img VALUES ('bad', 'x', 'not json')")
        # nothing left to do
        self.assertEqual(dbcharset.normalize(connection, verbosity=0), 0)

    @unittest.skipUnless(MYSQL and connection.mysql_is_mariadb, "MariaDB's long unique keys")
    def test_keeps_a_key_whose_index_becomes_a_long_unique_key(self):
        # as jobqueue_jobserveraddress on a database from an older release:
        # in latin1 the integer key's only index is the unique (js_id, address)
        # one, which utf8mb4 turns into a hash that can't back a foreign key
        self.sql("CREATE TABLE t526_js (id int PRIMARY KEY) ENGINE=InnoDB DEFAULT CHARSET=latin1",
                 "CREATE TABLE t526_addr (id int AUTO_INCREMENT PRIMARY KEY, js_id int NOT NULL, "
                 "address varchar(1024) NOT NULL, UNIQUE KEY t526_addr_u (js_id, address), "
                 "CONSTRAINT t526_addr_js FOREIGN KEY (js_id) REFERENCES t526_js (id)) "
                 "ENGINE=InnoDB DEFAULT CHARSET=latin1")
        keys = self.keys()
        self.assertIn("t526_addr_js", [k[0] for k in keys])
        dbcharset.normalize(connection, verbosity=0)
        self.assertEqual(self.keys(), keys)
        # and it's enforced
        from django.db import IntegrityError
        with self.assertRaises(IntegrityError):
            self.sql("INSERT INTO t526_addr (js_id, address) VALUES (99, 'x')")

    def test_collision_stops_before_any_change(self):
        self.sql("CREATE TABLE t526_names (name varchar(20) NOT NULL UNIQUE) "
                 "ENGINE=InnoDB DEFAULT CHARSET=latin1 COLLATE=latin1_swedish_ci",
                 # different in latin1_swedish_ci, the same in the utf8mb4 _ci collations
                 "INSERT INTO t526_names VALUES ('a'), (_latin1 X'E4')")
        before = self.collations(), self.keys()
        with self.assertRaisesRegex(dbcharset.CharsetError, "t526_names"):
            dbcharset.normalize(connection, verbosity=0)
        self.assertEqual((self.collations(), self.keys()), before)

    def test_adds_back_keys_after_an_interrupted_run(self):
        from django.db.backends.utils import CursorWrapper
        keys = self.keys()
        real = CursorWrapper.execute

        def killed_at_convert(cursor, sql, params=None):
            # a run killed after it dropped the keys, before it converted anything
            if "CONVERT TO CHARACTER SET" in sql:
                raise KeyboardInterrupt
            return real(cursor, sql, params)

        with mock.patch.object(CursorWrapper, "execute", killed_at_convert):
            with self.assertRaises(KeyboardInterrupt):
                dbcharset.normalize(connection, verbosity=0)
        # the keys were saved, then dropped
        self.assertEqual(self.keys(), [])
        self.assertEqual(self.sql("SELECT COUNT(*) FROM %s" % dbcharset.BACKUP_TABLE), ((3,),))
        self.assertEqual(dbcharset.normalize(connection, verbosity=0), 3)
        self.assertEqual(self.keys(), keys)
        self.assertEqual(set(self.collations().values()), {self.collation})
        self.assertFalse(self.sql("SHOW TABLES LIKE '%s'" % dbcharset.BACKUP_TABLE))
