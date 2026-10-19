import os
import tempfile

from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings

from scripts.models import Script, ScriptType


@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class ScriptSaveTests(TestCase):
  """ Script and playbook files are stored under the script type's directory, and removed with the script. """

  def setUp(self):
    self.script_type = ScriptType.objects.create(name="Post Boot", slug="post-boot")

  def test_deleting_a_script_deletes_its_file(self):
    script = Script(name="hello", scriptType=self.script_type, filename=SimpleUploadedFile("hello.sh", b"echo hi\n"))
    script.save()
    path = os.path.join(settings.MEDIA_ROOT, script.filename.name)
    self.assertTrue(os.path.isfile(path))
    script.delete()
    self.assertFalse(os.path.exists(path))

  def test_deleting_a_script_without_a_file(self):
    Script(name="no file", slug="no-file2", scriptType=self.script_type).save()
    Script.objects.get(pk="no-file2").delete()
    self.assertFalse(Script.objects.filter(pk="no-file2").exists())
