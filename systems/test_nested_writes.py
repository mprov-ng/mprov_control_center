import tempfile

from django.contrib.auth.models import User
from django.test import TestCase, override_settings

from systems.models import SystemGroup


@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class NestedWritableSerializerTests(TestCase):
  """ /systemgroups/, /systemimages/ and /scripts/ accept IDs on POST and still return nested objects. """

  def setUp(self):
    from scripts.models import Script, ScriptType
    self.user = User.objects.create_superuser("admin", "admin@example.com", "password")
    self.client.force_login(self.user)
    self.script_type = ScriptType.objects.create(name="Post Boot", slug="post-boot")
    self.script = Script(name="hello", slug="hellosh", scriptType=self.script_type)
    self.script.save()

  def post_json(self, url, data):
    import json
    return self.client.post(url, json.dumps(data), content_type="application/json")

  def test_create_system_group_with_script_ids(self):
    response = self.post_json("/systemgroups/", {"name": "compute", "scripts": ["hellosh"]})
    self.assertEqual(response.status_code, 201, response.content)
    group = SystemGroup.objects.get(name="compute")
    self.assertEqual([s.pk for s in group.scripts.all()], ["hellosh"])
    script = response.json()["scripts"][0]
    self.assertEqual((script["slug"], script["scriptType"]["slug"]), ("hellosh", "post-boot"))

  def test_create_system_group_without_related(self):
    self.assertEqual(self.post_json("/systemgroups/", {"name": "login"}).status_code, 201)

  def test_create_system_image_with_group_ids(self):
    group = SystemGroup.objects.create(name="compute")
    response = self.post_json("/systemimages/", {"name": "compute-img", "created_by": self.user.pk,
                                                 "systemgroups": [group.pk], "jobservers": []})
    self.assertEqual(response.status_code, 201, response.content)
    self.assertEqual(response.json()["systemgroups"][0]["name"], "compute")

  def test_create_script_with_type_id(self):
    from django.core.files.uploadedfile import SimpleUploadedFile
    response = self.client.post("/scripts/", {"name": "new", "scriptType": "post-boot",
                                              "filename": SimpleUploadedFile("new.sh", b"echo new\n")})
    self.assertEqual(response.status_code, 201, response.content)
    self.assertEqual(response.json()["scriptType"], {"name": "Post Boot", "slug": "post-boot"})

  def test_list_is_still_nested(self):
    group = SystemGroup.objects.create(name="compute")
    group.scripts.add(self.script)
    response = self.client.get("/systemgroups/", CONTENT_TYPE="application/json")
    script = response.json()[0]["scripts"][0]
    self.assertEqual(script["scriptType"], {"name": "Post Boot", "slug": "post-boot"})
    self.assertEqual(script["name"], "hello")
