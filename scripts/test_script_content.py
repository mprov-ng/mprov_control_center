import os
import tempfile

from django.conf import settings
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from rest_framework import serializers

from scripts.models import Script, ScriptType
from scripts.serializers import ScriptAPISerializer


@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class ScriptContentTests(TestCase):
  """ A script can be uploaded as a file or written as content; either way it's
  stored as <type>/<slug>-v<version>, and content edits are kept. """

  def setUp(self):
    self.script_type = ScriptType.objects.create(name="Post Boot", slug="post-boot")

  def on_disk(self, script):
    script = Script.objects.get(pk=script.pk)
    with open(os.path.join(settings.MEDIA_ROOT, script.filename.name)) as f:
      return script.filename.name, f.read()

  def test_content_only_script_is_written_to_a_file(self):
    script = Script(name="Set Root PW", scriptType=self.script_type, content="echo root\n")
    script.save()
    self.assertEqual(script.slug, "set-root-pw")
    self.assertEqual(self.on_disk(script), ("post-boot/set-root-pw-v1", "echo root\n"))

  def test_content_only_script_keeps_a_given_slug(self):
    script = Script(name="x", slug="set_root_pwsh", scriptType=self.script_type, content="echo root\n")
    script.save()
    self.assertEqual(self.on_disk(script)[0], "post-boot/set_root_pwsh-v1")

  def test_upload_is_stored_under_the_slug(self):
    script = Script(name="hello", scriptType=self.script_type, filename=SimpleUploadedFile("hello.sh", b"echo one\n"))
    script.save()
    self.assertEqual(self.on_disk(script), ("post-boot/hellosh-v1", "echo one\n"))

  def test_content_edit_is_kept(self):
    script = Script(name="hello", scriptType=self.script_type, filename=SimpleUploadedFile("hello.sh", b"echo one\n"))
    script.save()
    script = Script.objects.get(pk=script.pk)
    script.content = "echo two\n"
    script.save()
    self.assertEqual(self.on_disk(script), ("post-boot/hellosh-v1", "echo two\n"))

  def test_new_upload_replaces_the_content(self):
    script = Script(name="hello", scriptType=self.script_type, content="echo one\n")
    script.save()
    script = Script.objects.get(pk=script.pk)
    script.filename = SimpleUploadedFile("hello.sh", b"echo three\n")
    script.save()
    self.assertEqual(self.on_disk(script), ("post-boot/hello-v1", "echo three\n"))

  def test_save_without_content_keeps_the_file(self):
    script = Script(name="hello", scriptType=self.script_type, content="echo one\n")
    script.save()
    script = Script.objects.get(pk=script.pk)
    script.name = "renamed"
    script.save()
    self.assertEqual(self.on_disk(script), ("post-boot/hello-v1", "echo one\n"))

  def test_neither_file_nor_content_is_invalid(self):
    with self.assertRaises(ValidationError):
      Script(name="empty", slug="empty", scriptType=self.script_type).clean()
    with self.assertRaises(serializers.ValidationError):
      ScriptAPISerializer().validate({})
    ScriptAPISerializer().validate({"content": "echo hi\n"})


@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class ScriptAdminContentTests(TestCase):
  """ The admin can add a script with content and no file, and edit its content. """

  def setUp(self):
    self.client.force_login(User.objects.create_superuser("admin", "admin@example.com", "password"))
    ScriptType.objects.create(name="Post Boot", slug="post-boot")

  def post(self, url, **data):
    data.update({"scriptType": "post-boot", "version": 1, "_save": "Save"})
    return self.client.post(url, data)

  def test_add_and_edit_without_a_file(self):
    response = self.post("/admin/scripts/script/add/", name="motd", content="echo hi\n")
    self.assertEqual(response.status_code, 302, response.content.decode()[:2000])
    script = Script.objects.get(name="motd")
    self.post(f"/admin/scripts/script/{script.pk}/change/", name="motd", content="echo bye\n")
    with open(os.path.join(settings.MEDIA_ROOT, Script.objects.get(pk=script.pk).filename.name)) as f:
      # the admin form strips surrounding whitespace, as it always has.
      self.assertEqual(f.read(), "echo bye")

  def test_add_with_neither_is_rejected(self):
    response = self.post("/admin/scripts/script/add/", name="empty", content="")
    self.assertEqual(response.status_code, 200)
    self.assertIn("Upload a script file or enter its content.", response.content.decode())
    self.assertFalse(Script.objects.exists())
