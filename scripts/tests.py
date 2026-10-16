import json
import os
import tempfile

from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import resolve

from common.testing import APITestCase
from scripts.models import AnsibleCollection, AnsiblePlaybook, AnsibleRole, File, Script, ScriptType
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


@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class ScriptsAPIEndpointTests(APITestCase):
  """ The endpoints the scripts models name (File.endpoint and so on) are routed. """

  def setUp(self):
    super().setUp()
    ScriptType.objects.create(name="Post Boot", slug="post-boot")

  def test_every_model_endpoint_resolves(self):
    for model in (Script, File, AnsiblePlaybook, AnsibleRole, AnsibleCollection):
      self.assertEqual(resolve(model.endpoint).func.view_class.model, model, model.endpoint)

  def test_files(self):
    response = self.client.post("/files/", {"name": "motd", "filename": SimpleUploadedFile("motd.txt", b"hi\n")})
    self.assertEqual(response.status_code, 201, response.content)
    slug = response.json()["slug"]
    self.assertEqual(self.get_json(f"/files/{slug}/").json()["name"], "motd")

  def test_playbooks(self):
    response = self.client.post("/ansibleplaybook/", {"name": "site", "scriptType": "post-boot",
                                                      "filename": SimpleUploadedFile("site.yaml", b"- hosts: all\n")})
    self.assertEqual(response.status_code, 201, response.content)
    self.assertEqual(response.json()["scriptType"]["slug"], "post-boot")

  def test_roles_and_collections(self):
    for url, field, value in (("/ansiblerole/", "roleurl", "https://github.com/example/ansible.role.ntp"),
                              ("/ansiblecollection/", "collectionurl", "community.general")):
      response = self.client.post(url, json.dumps({"name": "x", field: value, "scriptType": "post-boot"}),
                                  content_type="application/json")
      self.assertEqual(response.status_code, 201, response.content)
      slug = response.json()["slug"]
      self.assertEqual(self.get_json(f"{url}{slug}/").status_code, 200)
      self.assertEqual(self.client.delete(f"{url}{slug}/").status_code, 204)
