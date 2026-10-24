import json

from common.testing import APITestCase
from osmanagement.models import OSDistro


class OSDistroRootPwTests(APITestCase):
  """ The distro root password is write-only, like the BMC password (#313).
  POST/PATCH accept rootpw; no /distros/ GET returns it. """

  SECRET = "r00t$ecret-hash"

  def setUp(self):
    super().setUp()
    self.distro = OSDistro.objects.create(name="Rocky 9", vendor="Rocky", version="9",
                                          baseurl="http://mirror/", rootpw=self.SECRET)

  def get_json(self, url):
    return self.client.get(url, CONTENT_TYPE="application/json")

  def test_list_hides_rootpw(self):
    response = self.get_json("/distros/")
    self.assertEqual(response.status_code, 200, response.content)
    distros = response.json()
    self.assertIn("Rocky 9", [d["name"] for d in distros])
    for distro in distros:
      self.assertNotIn("rootpw", distro)
    self.assertNotIn(self.SECRET, response.content.decode())

  def test_single_get_hides_rootpw(self):
    response = self.get_json(f"/distros/{self.distro.id}/")
    self.assertEqual(response.status_code, 200, response.content)
    self.assertNotIn("rootpw", response.json())
    self.assertNotIn(self.SECRET, response.content.decode())

  def test_detail_list_hides_rootpw(self):
    response = self.get_json("/distros/?detail")
    self.assertEqual(response.status_code, 200, response.content)
    for distro in response.json():
      self.assertNotIn("rootpw", distro)
    self.assertNotIn(self.SECRET, response.content.decode())

  def test_post_accepts_rootpw_without_returning_it(self):
    response = self.client.post("/distros/", json.dumps(
        {"name": "Fedora 41", "vendor": "Fedora", "version": "41",
         "baseurl": "http://mirror/", "rootpw": self.SECRET}),
        content_type="application/json")
    self.assertEqual(response.status_code, 201, response.content)
    self.assertEqual(OSDistro.objects.get(name="Fedora 41").rootpw, self.SECRET)
    self.assertNotIn("rootpw", response.json())

  def test_patch_accepts_rootpw_without_returning_it(self):
    response = self.client.patch(f"/distros/{self.distro.id}/", json.dumps({"rootpw": self.SECRET}),
                                 content_type="application/json")
    self.assertEqual(response.status_code, 200, response.content)
    self.assertEqual(OSDistro.objects.get(pk=self.distro.pk).rootpw, self.SECRET)
    self.assertNotIn("rootpw", response.json())
