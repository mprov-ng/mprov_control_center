import json

from common.testing import APITestCase
from jobqueue.models import JobModule


class JobModuleCreateTests(APITestCase):
  """ POST /jobmodules/ sets the module ID; PATCH can't change it. """

  def test_create_with_slug(self):
    response = self.client.post("/jobmodules/", json.dumps({"slug": "ldap-sync", "name": "LDAP Sync"}), content_type="application/json")
    self.assertEqual(response.status_code, 201, response.content)
    self.assertEqual(JobModule.objects.get(pk="ldap-sync").name, "LDAP Sync")

  def test_duplicate_slug_is_400(self):
    JobModule.objects.create(slug="nads", name="NADS")
    response = self.client.post("/jobmodules/", json.dumps({"slug": "nads", "name": "Other"}), content_type="application/json")
    self.assertEqual(response.status_code, 400)

  def test_patch_cannot_change_slug(self):
    JobModule.objects.create(slug="nads", name="NADS")
    response = self.client.patch("/jobmodules/nads/", json.dumps({"slug": "other"}), content_type="application/json")
    self.assertEqual(response.status_code, 400)
    response = self.client.patch("/jobmodules/nads/", json.dumps({"name": "Node Detection"}), content_type="application/json")
    self.assertEqual(response.status_code, 200, response.content)
    self.assertEqual(list(JobModule.objects.values_list("slug", "name")), [("nads", "Node Detection")])
