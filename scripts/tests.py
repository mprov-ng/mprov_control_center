import os
import tempfile

from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import resolve

from scripts.models import AnsiblePlaybook, Script, ScriptType
from scripts.views import ScriptAPIView


class ScriptURLTests(SimpleTestCase):
  """ /scripts/<pk>/ takes a script slug. """

  def test_detail_route_takes_slug(self):
    match = resolve("/scripts/extra_packagessh/")
    self.assertEqual(match.func.view_class, ScriptAPIView)
    self.assertEqual(match.kwargs, {"pk": "extra_packagessh"})


@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class ScriptSaveTests(TestCase):
  """ Script and playbook files are stored under the script type's directory, and removed with the script. """

  def setUp(self):
    self.script_type = ScriptType.objects.create(name="Post Boot", slug="post-boot")

  def test_save_without_a_file(self):
    Script(name="no file", slug="no-file", scriptType=self.script_type, content="echo hi").save()
    self.assertEqual(Script.objects.get(pk="no-file").name, "no file")

  def test_playbook_dir_matches_the_stored_path(self):
    playbook = AnsiblePlaybook(name="site", scriptType=self.script_type,
                               filename=SimpleUploadedFile("site.yaml", b"- hosts: all\n"))
    playbook.save()
    self.assertEqual(playbook.filename.name, "post-boot/ansibleplaybooks/siteyaml-v1")
    self.assertTrue(os.path.isfile(os.path.join(settings.MEDIA_ROOT, playbook.filename.name)))
    self.assertFalse(os.path.exists(os.path.join(settings.MEDIA_ROOT, "ansibleplaybooks")))

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
