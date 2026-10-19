import json
import tempfile

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.urls import resolve

from common.testing import APITestCase
from scripts.models import AnsibleCollection, AnsiblePlaybook, AnsibleRole, File, Script, ScriptType


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
