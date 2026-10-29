import json
import tempfile

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db.models import ProtectedError
from django.test import override_settings

from common.testing import APITestCase
from scripts.models import AnsiblePlaybook, Script, ScriptType


@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class ScriptTypeProtectTests(APITestCase):
  """ A script type in use can't be deleted, and a script whose type is gone doesn't crash (#310). """

  def setUp(self):
    super().setUp()
    self.script_type = ScriptType.objects.create(name="Post Boot", slug="post-boot")
    self.script = Script.objects.create(name="hello", slug="hello", scriptType=self.script_type, content="echo hi")
    self.playbook = AnsiblePlaybook.objects.create(name="site", scriptType=self.script_type,
                                                   filename=SimpleUploadedFile("site.yaml", b"- hosts: all\n"))

  def typeless(self):
    # how a type deletion left them before PROTECT.
    Script.objects.update(scriptType=None)
    AnsiblePlaybook.objects.update(scriptType=None)
    return Script.objects.get(pk="hello"), AnsiblePlaybook.objects.get(pk=self.playbook.pk)

  def test_type_in_use_cant_be_deleted(self):
    with self.assertRaises(ProtectedError):
      self.script_type.delete()
    self.script.delete()
    with self.assertRaises(ProtectedError):
      self.script_type.delete()
    self.playbook.delete()
    self.script_type.delete()
    self.assertFalse(ScriptType.objects.exists())

  def test_typeless_str(self):
    script, _ = self.typeless()
    self.assertEqual(str(script), "(?) hello")

  def test_typeless_save_asks_for_a_type(self):
    script, playbook = self.typeless()
    for obj in (script, playbook):
      with self.assertRaises(ValidationError) as cm:
        obj.save()
      self.assertIn("scriptType", cm.exception.message_dict)

  def test_typeless_api_patch(self):
    self.typeless()
    for url in ("/scripts/hello/", f"/ansibleplaybook/{self.playbook.pk}/"):
      response = self.client.patch(url, json.dumps({"name": "renamed"}), content_type="application/json")
      self.assertEqual(response.status_code, 400, url)
      self.assertIn("scriptType", response.json())
      response = self.client.patch(url, json.dumps({"name": "renamed", "scriptType": "post-boot"}),
                                   content_type="application/json")
      self.assertEqual(response.status_code, 200, url)

  def test_admin_lists_with_a_typeless_script(self):
    # Script.__str__ used to raise, a 500 on every page with a script picker.
    self.typeless()
    for url in ("/admin/scripts/script/", "/admin/systems/system/add/"):
      self.assertEqual(self.client.get(url).status_code, 200, url)
