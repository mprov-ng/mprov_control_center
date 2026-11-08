"""
Bring every table of a MySQL/MariaDB database to one character set and
collation before migrations run (#526).

Databases first created by an older release can still have tables in
latin1_swedish_ci, while the database default (and so every table a new
migration creates) is utf8mb4.  Integer keys don't care, but a foreign key to
a string primary key does: MySQL/MariaDB refuse it (errno 150) unless both
columns have the same character set and collation.  So the first migration
that adds a foreign key or many-to-many field to an old table with a slug
primary key (scripts_file, systems_systemimage, ...) stops `migrate`, and
every migration after it, half way through an upgrade.

normalize() converts every table whose table or column collation differs from
the target to the target, before the migration plan runs.  The server won't
change the collation of a column that a foreign key uses, even with
foreign_key_checks off, so the foreign keys on those tables are dropped first
and added back afterwards.  Their definitions are saved in BACKUP_TABLE before
any is dropped, so a run that's killed half way adds them back the next time.

It's run from a pre_migrate handler (systems/apps.py), so on every `migrate`;
once the database is consistent it's one information_schema query.
"""
import re
import sys
from collections import OrderedDict

BACKUP_TABLE = "mprov_charset_fk_backup"


class CharsetError(Exception):
    """ The tables can't be converted as they are. """


def qn(name):
    """ A quoted identifier. """
    return "`" + name.replace("`", "``") + "`"


def target_collation(cursor):
    """ The utf8mb4 collation tables should have: the database's default if
    that's utf8mb4, else the server's, else utf8mb4's own default. """
    cursor.execute("SELECT DEFAULT_CHARACTER_SET_NAME, DEFAULT_COLLATION_NAME "
                   "FROM information_schema.SCHEMATA WHERE SCHEMA_NAME = DATABASE()")
    charset, collation = cursor.fetchone()
    if charset == "utf8mb4":
        return collation
    cursor.execute("SELECT @@collation_server")
    server = cursor.fetchone()[0]
    if server.split("_", 1)[0] == "utf8mb4":
        return server
    cursor.execute("SHOW CHARACTER SET LIKE 'utf8mb4'")
    return cursor.fetchone()[2]


def tables_to_convert(cursor, collation):
    """ {table: row format} for each base table whose default collation isn't
    collation, or that has a column in another character set.  A utf8mb4
    column with its own collation doesn't count: Django gives MariaDB's JSON
    columns utf8mb4_bin on purpose. """
    cursor.execute(
        "SELECT t.TABLE_NAME, t.ROW_FORMAT FROM information_schema.TABLES t "
        "WHERE t.TABLE_SCHEMA = DATABASE() AND t.TABLE_TYPE = 'BASE TABLE' AND t.TABLE_NAME <> %s "
        "AND (t.TABLE_COLLATION <> %s OR EXISTS (SELECT 1 FROM information_schema.COLUMNS c "
        "WHERE c.TABLE_SCHEMA = t.TABLE_SCHEMA AND c.TABLE_NAME = t.TABLE_NAME "
        "AND c.CHARACTER_SET_NAME IS NOT NULL AND c.CHARACTER_SET_NAME <> 'utf8mb4')) ORDER BY t.TABLE_NAME",
        [BACKUP_TABLE, collation])
    return OrderedDict(cursor.fetchall())


def string_columns(cursor, tables, collation):
    """ {(table, column): collation it ends up with} for the character columns
    of tables.  That's collation, except for a binary column in a table whose
    default isn't binary (a JSON column on MariaDB), which stays binary. """
    if not tables:
        return {}
    cursor.execute(
        "SELECT c.TABLE_NAME, c.COLUMN_NAME, c.COLLATION_NAME, t.TABLE_COLLATION "
        "FROM information_schema.COLUMNS c JOIN information_schema.TABLES t "
        "ON t.TABLE_SCHEMA = c.TABLE_SCHEMA AND t.TABLE_NAME = c.TABLE_NAME "
        "WHERE c.TABLE_SCHEMA = DATABASE() AND c.COLLATION_NAME IS NOT NULL "
        "AND c.TABLE_NAME IN (%s)" % ", ".join(["%s"] * len(tables)), list(tables))
    return {(table, column): BINARY if deliberate(own, table_default) else collation
            for table, column, own, table_default in cursor.fetchall()}


BINARY = "utf8mb4_bin"


def deliberate(column_collation, table_collation):
    """ Whether a column's binary collation was chosen for it, rather than
    inherited from its table. """
    return column_collation != table_collation and column_collation.endswith("_bin")


def column_definitions(cursor, table):
    """ {column: its definition line from SHOW CREATE TABLE}. """
    cursor.execute("SHOW CREATE TABLE %s" % qn(table))
    lines = {}
    for line in cursor.fetchone()[1].splitlines():
        line = line.strip().rstrip(",")
        if line.startswith("`"):
            name = line[1:].split("`", 1)[0]
            lines[name.replace("``", "`")] = line
    return lines


def as_binary(definition):
    """ A column definition, in utf8mb4_bin instead of its own collation. """
    return re.sub(r"(CHARACTER SET \w+ )?COLLATE \w+", "CHARACTER SET utf8mb4 COLLATE " + BINARY, definition, count=1)


def foreign_keys(cursor):
    """ [(table, name, sql adding it back, columns, referenced table, referenced columns)]
    for each foreign key in this database. """
    cursor.execute(
        "SELECT k.TABLE_NAME, k.CONSTRAINT_NAME, k.COLUMN_NAME, k.REFERENCED_TABLE_NAME, "
        "k.REFERENCED_COLUMN_NAME, r.UPDATE_RULE, r.DELETE_RULE "
        "FROM information_schema.KEY_COLUMN_USAGE k JOIN information_schema.REFERENTIAL_CONSTRAINTS r "
        "ON r.CONSTRAINT_SCHEMA = k.CONSTRAINT_SCHEMA AND r.TABLE_NAME = k.TABLE_NAME "
        "AND r.CONSTRAINT_NAME = k.CONSTRAINT_NAME "
        "WHERE k.TABLE_SCHEMA = DATABASE() AND k.REFERENCED_TABLE_SCHEMA = DATABASE() "
        "ORDER BY k.TABLE_NAME, k.CONSTRAINT_NAME, k.ORDINAL_POSITION")
    keys = OrderedDict()
    for table, name, column, ref_table, ref_column, on_update, on_delete in cursor.fetchall():
        key = keys.setdefault((table, name), dict(columns=[], ref_table=ref_table, ref_columns=[],
                                                   on_update=on_update, on_delete=on_delete))
        key["columns"].append(column)
        key["ref_columns"].append(ref_column)
    result = []
    for (table, name), k in keys.items():
        sql = "ALTER TABLE %s ADD CONSTRAINT %s FOREIGN KEY (%s) REFERENCES %s (%s)" % (
            qn(table), qn(name), ", ".join(qn(c) for c in k["columns"]), qn(k["ref_table"]),
            ", ".join(qn(c) for c in k["ref_columns"]))
        # RESTRICT is what a key without the clause (as Django makes them)
        # reads back as; naming it would read back as NO ACTION on MariaDB
        for clause, rule in (("ON DELETE", k["on_delete"]), ("ON UPDATE", k["on_update"])):
            if rule != "RESTRICT":
                sql += " %s %s" % (clause, rule)
        result.append((table, name, sql, k["columns"], k["ref_table"], k["ref_columns"]))
    return result


def collisions(cursor, tables, strings):
    """ ["table.index"] for each unique index of tables with two rows whose
    values would be equal in the collations they're converted to (strings),
    though they differ now (e.g. "a" and "ä" are different in
    latin1_swedish_ci, the same in utf8mb4_general_ci).  Converting such a
    table would fail half way. """
    if not tables:
        return []
    cursor.execute(
        "SELECT s.TABLE_NAME, s.INDEX_NAME, s.COLUMN_NAME, c.COLLATION_NAME IS NOT NULL "
        "FROM information_schema.STATISTICS s JOIN information_schema.COLUMNS c "
        "ON c.TABLE_SCHEMA = s.TABLE_SCHEMA AND c.TABLE_NAME = s.TABLE_NAME AND c.COLUMN_NAME = s.COLUMN_NAME "
        "WHERE s.TABLE_SCHEMA = DATABASE() AND s.NON_UNIQUE = 0 AND s.TABLE_NAME IN (%s) "
        "ORDER BY s.TABLE_NAME, s.INDEX_NAME, s.SEQ_IN_INDEX" % ", ".join(["%s"] * len(tables)), list(tables))
    indexes = OrderedDict()
    for table, index, column, is_string in cursor.fetchall():
        indexes.setdefault((table, index), []).append((column, bool(is_string)))
    found = []
    for (table, index), columns in indexes.items():
        if not any(is_string for _, is_string in columns):
            continue
        exprs = [("CONVERT(%s USING utf8mb4) COLLATE %s" % (qn(c), strings[(table, c)])) if s else qn(c)
                 for c, s in columns]
        cursor.execute("SELECT 1 FROM %s WHERE %s GROUP BY %s HAVING COUNT(*) > 1 LIMIT 1" % (
            qn(table), " AND ".join("%s IS NOT NULL" % qn(c) for c, _ in columns), ", ".join(exprs)))
        if cursor.fetchone():
            found.append("%s.%s" % (table, index))
    return found


def saved_foreign_keys(cursor):
    """ [(table, name, sql)] saved by a run that didn't finish. """
    cursor.execute("SELECT COUNT(*) FROM information_schema.TABLES "
                   "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s", [BACKUP_TABLE])
    if not cursor.fetchone()[0]:
        return []
    cursor.execute("SELECT tbl, name, definition FROM %s ORDER BY tbl, name" % qn(BACKUP_TABLE))
    return list(cursor.fetchall())


def normalize(connection, stdout=None, verbosity=1):
    """ Convert connection's tables to one utf8mb4 collation, keeping their
    foreign keys.  Returns the number of tables converted. """
    if connection.vendor != "mysql":
        return 0
    out = stdout or sys.stdout

    def say(msg):
        if verbosity:
            out.write(msg + "\n")

    with connection.cursor() as cursor:
        collation = target_collation(cursor)
        tables = tables_to_convert(cursor, collation)
        pending = saved_foreign_keys(cursor)
        if not tables and not pending:
            return 0

        strings = string_columns(cursor, tables, collation)
        clashes = collisions(cursor, tables, strings)
        if clashes:
            raise CharsetError(
                "Can't convert the database's tables to %s: these unique indexes have values that would be "
                "duplicates under it: %s.  Make the values distinct, then run migrate again." % (
                    collation, ", ".join(clashes)))

        # binary columns get their own definition back after the conversion
        keep_binary = OrderedDict()
        for table in tables:
            columns = [c for (t, c), coll in strings.items() if t == table and coll == BINARY]
            if columns:
                lines = column_definitions(cursor, table)
                keep_binary[table] = [as_binary(lines[c]) for c in columns]

        # Every foreign key on these tables, not just those on string
        # columns: when the conversion turns an integer key's only index into
        # a long unique (hash) key, which can't back a foreign key (as
        # jobqueue_jobserveraddress has, unique on (jobserver_id, a 1024
        # character address)), MariaDB keeps the key in InnoDB but no longer
        # shows or enforces it, and it can't be added back.  Added back after
        # the conversion, it gets an index of its own, as on a new install.
        drop = [(t, n, sql) for t, n, sql, cols, ref_t, ref_cols in foreign_keys(cursor)
                if t in tables or ref_t in tables]

        if tables:
            say("Converting %d table%s to %s, so new foreign keys match the existing ones..." % (
                len(tables), "" if len(tables) == 1 else "s", collation))
        cursor.execute("SET SESSION foreign_key_checks = 0")
        try:
            cursor.execute("CREATE TABLE IF NOT EXISTS %s (tbl varchar(64) NOT NULL, name varchar(64) NOT NULL, "
                           "definition text NOT NULL, PRIMARY KEY (tbl, name)) "
                           "ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=%s" % (qn(BACKUP_TABLE), collation))
            # save every definition before dropping any
            for table, name, sql in drop:
                cursor.execute("REPLACE INTO %s (tbl, name, definition) VALUES (%%s, %%s, %%s)" % qn(BACKUP_TABLE),
                               [table, name, sql])
            for table, name, sql in drop:
                cursor.execute("ALTER TABLE %s DROP FOREIGN KEY %s" % (qn(table), qn(name)))

            for table, row_format in tables.items():
                # utf8mb4 keys need DYNAMIC's longer index prefixes
                extra = ", ROW_FORMAT=DYNAMIC" if (row_format or "").lower() in ("compact", "redundant") else ""
                cursor.execute("ALTER TABLE %s CONVERT TO CHARACTER SET utf8mb4 COLLATE %s%s" % (
                    qn(table), collation, extra))
                if table in keep_binary:
                    cursor.execute("ALTER TABLE %s %s" % (
                        qn(table), ", ".join("MODIFY " + d for d in keep_binary[table])))

            cursor.execute("SELECT DEFAULT_COLLATION_NAME FROM information_schema.SCHEMATA "
                           "WHERE SCHEMA_NAME = DATABASE()")
            if cursor.fetchone()[0] != collation:
                cursor.execute("SELECT DATABASE()")
                cursor.execute("ALTER DATABASE %s CHARACTER SET utf8mb4 COLLATE %s" % (
                    qn(cursor.fetchone()[0]), collation))

            existing = {(t, n) for t, n, *_ in foreign_keys(cursor)}
            for table, name, sql in saved_foreign_keys(cursor):
                if (table, name) not in existing:
                    cursor.execute(sql)
                cursor.execute("DELETE FROM %s WHERE tbl = %%s AND name = %%s" % qn(BACKUP_TABLE), [table, name])
            cursor.execute("DROP TABLE %s" % qn(BACKUP_TABLE))
        finally:
            cursor.execute("SET SESSION foreign_key_checks = 1")
        if pending and not tables:
            say("Added back %d foreign key%s left out by an earlier conversion." % (
                len(pending), "" if len(pending) == 1 else "s"))
    return len(tables)


def normalize_before_migrate(sender, using="default", verbosity=1, stdout=None, **kwargs):
    """ pre_migrate handler. """
    from django.db import connections
    normalize(connections[using], stdout=stdout, verbosity=verbosity)
