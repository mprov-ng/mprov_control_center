import json

from common.testing import APITestCase
from osmanagement.models import OSRepo


class OSManagementCreateTests(APITestCase):
  """ POST /repos/ and /distros/ don't need the optional relations. """

  def post_json(self, url, data):
    return self.client.post(url, json.dumps(data), content_type="application/json")

  def test_create_repo(self):
    response = self.post_json("/repos/", {"name": "extras", "repo_package_url": "http://mirror/extras/"})
    self.assertEqual(response.status_code, 201, response.content)
    self.assertIsNone(OSRepo.objects.get(name="extras").ostype)

  def test_create_distro(self):
    response = self.post_json("/distros/", {"name": "Rocky 9", "vendor": "Rocky", "version": "9", "baseurl": "http://mirror/"})
    self.assertEqual(response.status_code, 201, response.content)
