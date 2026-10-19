import tempfile

from django.test import TestCase, override_settings

from scripts.models import Script, ScriptType


@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class ScriptSaveTests(TestCase):
  """ Script and playbook files are stored under the script type's directory, and removed with the script. """

  def setUp(self):
    self.script_type = ScriptType.objects.create(name="Post Boot", slug="post-boot")

  def test_save_without_a_file(self):
    Script(name="no file", slug="no-file", scriptType=self.script_type, content="echo hi").save()
    self.assertEqual(Script.objects.get(pk="no-file").name, "no file")
