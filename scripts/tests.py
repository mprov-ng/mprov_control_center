import tempfile

from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import resolve

from scripts.models import Script, ScriptType
from scripts.views import ScriptAPIView


class ScriptURLTests(SimpleTestCase):
  """ /scripts/<pk>/ takes a script slug. """

  def test_detail_route_takes_slug(self):
    match = resolve("/scripts/extra_packagessh/")
    self.assertEqual(match.func.view_class, ScriptAPIView)
    self.assertEqual(match.kwargs, {"pk": "extra_packagessh"})


@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class ScriptSaveTests(TestCase):
  """ Script.save() stores the script under its type's directory. """

  def setUp(self):
    self.script_type = ScriptType.objects.create(name="Post Boot", slug="post-boot")

  def test_save_without_a_file(self):
    Script(name="no file", slug="no-file", scriptType=self.script_type, content="echo hi").save()
    self.assertEqual(Script.objects.get(pk="no-file").name, "no file")
