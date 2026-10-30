from osmanagement.models import OSDistro

from common.testing import APITestCase
from systems.admin import SystemImageAdmin
from systems.models import SystemImage


class ImageAdminDistroColumnTests(APITestCase):
  """ The System Images admin list shows each image's OS Distribution (#171). """

  def setUp(self):
    super().setUp()
    self.distro = OSDistro.objects.create(name="Rocky 8", vendor="Rocky", version="8", baseurl="http://localhost/")
    self.image = SystemImage.objects.create(name="compute", created_by=self.user, osdistro=self.distro)

  def test_osdistro_is_in_list_display(self):
    self.assertIn("osdistro", SystemImageAdmin.list_display)

  def test_distro_name_shows_on_the_changelist(self):
    response = self.client.get("/admin/systems/systemimage/")
    self.assertEqual(response.status_code, 200)
    self.assertContains(response, "Rocky 8")

  def test_image_without_a_distro_still_renders(self):
    SystemImage.objects.create(name="no-distro", created_by=self.user)
    response = self.client.get("/admin/systems/systemimage/")
    self.assertEqual(response.status_code, 200)
