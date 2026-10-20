import os
import tempfile

from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings

from scripts.models import AnsiblePlaybook, ScriptType


@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class ScriptSaveTests(TestCase):
  """ Script and playbook files are stored under the script type's directory, and removed with the script. """

  def setUp(self):
    self.script_type = ScriptType.objects.create(name="Post Boot", slug="post-boot")

  def test_playbook_dir_matches_the_stored_path(self):
    playbook = AnsiblePlaybook(name="site", scriptType=self.script_type,
                               filename=SimpleUploadedFile("site.yaml", b"- hosts: all\n"))
    playbook.save()
    self.assertEqual(playbook.filename.name, "post-boot/ansibleplaybooks/siteyaml-v1")
    self.assertTrue(os.path.isfile(os.path.join(settings.MEDIA_ROOT, playbook.filename.name)))
    self.assertFalse(os.path.exists(os.path.join(settings.MEDIA_ROOT, "ansibleplaybooks")))
