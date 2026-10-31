import json

from django.core.exceptions import ValidationError

from common.testing import APITestCase
from osmanagement.models import OSDistro
from systems.models import SystemImage

URL = "https://dl.rockylinux.org/pub/rocky/9/images/x86_64/Rocky-9-Container-Base.latest.x86_64.tar.xz"
SHA = "sha256:" + "0123456789abcdef" * 4
CHECKSUM_URL = "https://dl.rockylinux.org/pub/rocky/9/images/x86_64/CHECKSUM"


class OSDistroBaseImageTests(APITestCase):
  """ The optional base image URL and checksum the job server builds images from (#429, mprov_jobserver#92). """

  def setUp(self):
    super().setUp()
    self.distro = OSDistro.objects.create(name="Rocky 9", vendor="Rocky", version="9", baseurl="http://mirror/")

  def patch(self, data):
    return self.client.patch(f"/distros/{self.distro.id}/", json.dumps(data), content_type="application/json")

  def assertRefused(self, data, field="base_image_checksum"):
    response = self.patch(data)
    self.assertEqual(response.status_code, 400, response.content)
    self.assertIn(field, response.json())
    self.distro.refresh_from_db()
    self.assertEqual((self.distro.base_image_url, self.distro.base_image_checksum), ("", ""))

  def test_empty_by_default(self):
    self.assertEqual((self.distro.base_image_url, self.distro.base_image_checksum), ("", ""))
    self.distro.full_clean()

  def test_distro_get_returns_them(self):
    distro = self.get_json(f"/distros/{self.distro.id}/").json()
    self.assertEqual((distro["base_image_url"], distro["base_image_checksum"]), ("", ""))

  def test_nested_in_the_image_detail(self):
    # the job server reads the distro from GET /systemimages/<slug>/.
    OSDistro.objects.filter(pk=self.distro.pk).update(base_image_url=URL, base_image_checksum=SHA)
    image = SystemImage.objects.create(name="compute", created_by=self.user, osdistro=self.distro)
    response = self.get_json(f"/systemimages/{image.slug}/")
    self.assertEqual(response.status_code, 200, response.content)
    osdistro = response.json()["osdistro"]
    self.assertEqual((osdistro["base_image_url"], osdistro["base_image_checksum"]), (URL, SHA))

  def test_patch_sets_url_with_a_sha256(self):
    response = self.patch({"base_image_url": URL, "base_image_checksum": SHA})
    self.assertEqual(response.status_code, 200, response.content)
    self.distro.refresh_from_db()
    self.assertEqual((self.distro.base_image_url, self.distro.base_image_checksum), (URL, SHA))

  def test_patch_sets_url_with_a_checksum_file_url(self):
    response = self.patch({"base_image_url": URL, "base_image_checksum": CHECKSUM_URL})
    self.assertEqual(response.status_code, 200, response.content)

  def test_url_without_a_checksum_is_refused(self):
    self.assertRefused({"base_image_url": URL})

  def test_malformed_sha256_is_refused(self):
    self.assertRefused({"base_image_url": URL, "base_image_checksum": "sha256:abc"})

  def test_other_checksum_text_is_refused(self):
    self.assertRefused({"base_image_url": URL, "base_image_checksum": "md5:abc"})

  def test_non_http_url_is_refused(self):
    self.assertRefused({"base_image_url": "ftp://mirror/image.tar.xz", "base_image_checksum": SHA}, field="base_image_url")

  def test_patch_checks_against_the_stored_checksum(self):
    OSDistro.objects.filter(pk=self.distro.pk).update(base_image_checksum=SHA)
    response = self.patch({"base_image_url": URL})
    self.assertEqual(response.status_code, 200, response.content)

  def test_clearing_the_checksum_of_a_stored_url_is_refused(self):
    OSDistro.objects.filter(pk=self.distro.pk).update(base_image_url=URL, base_image_checksum=SHA)
    response = self.patch({"base_image_checksum": ""})
    self.assertEqual(response.status_code, 400, response.content)
    self.distro.refresh_from_db()
    self.assertEqual(self.distro.base_image_checksum, SHA)

  def test_clearing_both_goes_back_to_dnf(self):
    OSDistro.objects.filter(pk=self.distro.pk).update(base_image_url=URL, base_image_checksum=SHA)
    response = self.patch({"base_image_url": "", "base_image_checksum": ""})
    self.assertEqual(response.status_code, 200, response.content)

  def test_post_without_them_works_as_before(self):
    response = self.client.post("/distros/", json.dumps({"name": "Rocky 8", "vendor": "Rocky", "version": "8",
                                                         "baseurl": "http://mirror/"}), content_type="application/json")
    self.assertEqual(response.status_code, 201, response.content)
    self.assertEqual(response.json()["base_image_url"], "")

  def test_post_url_without_a_checksum_is_refused(self):
    response = self.client.post("/distros/", json.dumps({"name": "Rocky 8", "vendor": "Rocky", "version": "8",
                                                         "baseurl": "http://mirror/", "base_image_url": URL}),
                                content_type="application/json")
    self.assertEqual(response.status_code, 400, response.content)
    self.assertFalse(OSDistro.objects.filter(name="Rocky 8").exists())

  def test_model_clean_refuses_url_without_a_checksum(self):
    # the admin form runs the model's full_clean().
    self.distro.base_image_url = URL
    with self.assertRaises(ValidationError) as caught:
      self.distro.full_clean()
    self.assertIn("base_image_checksum", caught.exception.message_dict)
    self.distro.base_image_checksum = SHA
    self.distro.full_clean()
