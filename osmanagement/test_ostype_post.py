import json

from common.testing import APITestCase
from osmanagement.models import OSType


class OSTypePostTests(APITestCase):
  """ POST /ostypes/ creates an OS type, or renames the one with the given slug. """

  def setUp(self):
    super().setUp()
    OSType.objects.create(slug="rhel", name="Old name")

  def post(self, data):
    return self.client.post("/ostypes/", json.dumps(data), content_type="application/json")

  def test_existing_slug_is_renamed(self):
    # how the jobserver's rhel modules register their OS type.
    response = self.post({"slug": "rhel", "name": "Yum/DNF Based Linux"})
    self.assertEqual(response.status_code, 200)
    self.assertEqual(OSType.objects.get(slug="rhel").name, "Yum/DNF Based Linux")

  def test_existing_slug_without_name_is_400(self):
    # issue #328: was a 500 from KeyError.
    response = self.post({"slug": "rhel"})
    self.assertEqual(response.status_code, 400)
    self.assertIn("name", response.json())
    self.assertEqual(OSType.objects.get(slug="rhel").name, "Old name")

  def test_new_slug_without_name_is_400(self):
    self.assertEqual(self.post({"slug": "debian"}).status_code, 400)
    self.assertFalse(OSType.objects.filter(slug="debian").exists())
