import tempfile

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings

from scripts.models import AnsibleCollection, AnsiblePlaybook, AnsibleRole, File, Script, ScriptType


@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class ConfigManagementListTests(TestCase):
  """ #496: the Config Management lists sort by name, search, filter by type
  (where they have one) and load the live search script. """

  def setUp(self):
    self.user = User.objects.create_superuser("admin", "admin@example.com", "password")
    self.client.force_login(self.user)
    self.post_boot = ScriptType.objects.create(name="Post Boot", slug="post-boot")
    self.image_gen = ScriptType.objects.create(name="Image Gen", slug="image-gen")
    # created out of name order, to check the default ordering.
    Script.objects.create(name="zz-last", scriptType=self.post_boot, content="echo z\n")
    Script.objects.create(name="aa-first", scriptType=self.image_gen, content="echo a\n")
    Script.objects.create(name="mm-middle", scriptType=self.post_boot, content="echo m\n")
    File.objects.create(name="motd", filename=SimpleUploadedFile("motd.txt", b"hi\n"))
    File.objects.create(name="hosts", filename=SimpleUploadedFile("hosts.txt", b"127.0.0.1\n"))
    AnsiblePlaybook.objects.create(name="site", scriptType=self.post_boot,
                                   filename=SimpleUploadedFile("site.yml", b"- hosts: all\n"))
    AnsiblePlaybook.objects.create(name="build", scriptType=self.image_gen,
                                   filename=SimpleUploadedFile("build.yml", b"- hosts: all\n"))
    AnsibleRole.objects.create(name="ntp", roleurl="https://example.com/roles/ntp.git", scriptType=self.post_boot)
    AnsibleRole.objects.create(name="users", roleurl="geerlingguy.users", scriptType=self.image_gen)
    AnsibleCollection.objects.create(name="posix", collectionurl="ansible.posix", scriptType=self.post_boot)
    AnsibleCollection.objects.create(name="general", collectionurl="community.general", scriptType=self.image_gen)

  def names(self, model, query=""):
    response = self.client.get(f"/admin/scripts/{model}/{query}")
    self.assertEqual(response.status_code, 200)
    return [obj.name for obj in response.context["cl"].result_list]

  def test_sorted_by_name(self):
    self.assertEqual(self.names("script"), ["aa-first", "mm-middle", "zz-last"])
    self.assertEqual(self.names("file"), ["hosts", "motd"])
    self.assertEqual(self.names("ansibleplaybook"), ["build", "site"])
    self.assertEqual(self.names("ansiblerole"), ["ntp", "users"])
    self.assertEqual(self.names("ansiblecollection"), ["general", "posix"])

  def test_search(self):
    self.assertEqual(self.names("script", "?q=middle"), ["mm-middle"])
    self.assertEqual(self.names("file", "?q=motd"), ["motd"])
    self.assertEqual(self.names("ansibleplaybook", "?q=site"), ["site"])
    self.assertEqual(self.names("ansiblerole", "?q=example.com"), ["ntp"])
    self.assertEqual(self.names("ansiblecollection", "?q=community"), ["general"])

  def test_type_filter_and_search_combine(self):
    self.assertEqual(self.names("script", f"?scriptType__slug__exact={self.post_boot.slug}"), ["mm-middle", "zz-last"])
    self.assertEqual(self.names("script", f"?scriptType__slug__exact={self.post_boot.slug}&q=zz"), ["zz-last"])
    self.assertEqual(self.names("ansibleplaybook", f"?scriptType__slug__exact={self.image_gen.slug}"), ["build"])
    self.assertEqual(self.names("ansiblerole", f"?scriptType__slug__exact={self.image_gen.slug}"), ["users"])
    self.assertEqual(self.names("ansiblecollection", f"?scriptType__slug__exact={self.post_boot.slug}"), ["posix"])

  def test_pages_load_live_search(self):
    for model in ("script", "file", "ansibleplaybook", "ansiblerole", "ansiblecollection"):
      response = self.client.get(f"/admin/scripts/{model}/")
      self.assertContains(response, "common/admin/js/live_search.js", msg_prefix=model)
      self.assertContains(response, 'id="searchbar"', msg_prefix=model)
