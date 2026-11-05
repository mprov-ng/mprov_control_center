import io
import json
import os
import stat
import tempfile

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings


class BackupDirTests(TestCase):
  """ mprov_backup writes to its own directory by default, which is a volume
  in the image, refuses the directories Apache serves, and makes its files
  readable by their owner only.  Its default used to be backups/ in the app
  directory, which an upgrade throws away (#457). """

  def setUp(self):
    tmp = tempfile.TemporaryDirectory()
    self.addCleanup(tmp.cleanup)
    self.tmp = tmp.name
    self.media = os.path.join(self.tmp, "media")
    self.static = os.path.join(self.tmp, "static")
    os.makedirs(self.media)
    os.makedirs(self.static)

  def backup(self, *args):
    with override_settings(MPROV_BACKUP_DIR=os.path.join(self.tmp, "backups"), MEDIA_ROOT=self.media, STATIC_ROOT=self.static):
      call_command("mprov_backup", *args, stdout=io.StringIO())

  def only_backup_in(self, path):
    entries = os.listdir(path)
    self.assertEqual(len(entries), 1)
    self.assertTrue(entries[0].startswith("mprov-backup-"))
    return os.path.join(path, entries[0])

  def test_writes_to_the_backup_dir_by_default(self):
    self.backup()
    backup_dir = self.only_backup_in(os.path.join(self.tmp, "backups"))
    with open(os.path.join(backup_dir, "manifest.json")) as fh:
      manifest = json.load(fh)
    for name in manifest["files"]:
      self.assertTrue(os.path.exists(os.path.join(backup_dir, name)))

  def test_output_dir_option(self):
    other = os.path.join(self.tmp, "elsewhere")
    self.backup("--output-dir", other)
    self.only_backup_in(other)

  def test_refuses_served_dirs(self):
    link = os.path.join(self.tmp, "db")
    os.symlink(self.media, link)
    for path in (self.media, os.path.join(self.media, "sub"), self.static, link):
      with self.assertRaises(CommandError, msg=path):
        self.backup("--output-dir", path)
    self.assertEqual(os.listdir(self.media), [])
    self.assertEqual(os.listdir(self.static), [])

  def test_a_dir_named_like_media_isnt_refused(self):
    # only media/ itself and what's under it: not media-old/.
    other = self.media + "-old"
    self.backup("--output-dir", other)
    self.only_backup_in(other)

  def test_owner_only_modes(self):
    old = os.umask(0o022)
    self.addCleanup(os.umask, old)
    self.backup()
    backup_dir = self.only_backup_in(os.path.join(self.tmp, "backups"))
    self.assertEqual(stat.S_IMODE(os.stat(backup_dir).st_mode), 0o700)
    for name in os.listdir(backup_dir):
      self.assertEqual(stat.S_IMODE(os.stat(os.path.join(backup_dir, name)).st_mode), 0o600, name)
    # and the umask is put back.
    self.assertEqual(os.umask(0o022), 0o022)
