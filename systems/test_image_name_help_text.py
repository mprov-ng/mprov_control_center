from common.testing import APITestCase
from systems.models import SystemImage


class ImageNameHelpTextTests(APITestCase):
  """ The System Images admin explains that changing the name makes a copy, not an in-place rename (#424). """

  def test_help_text_on_the_add_form(self):
    response = self.client.get("/admin/systems/systemimage/add/")
    self.assertEqual(response.status_code, 200)
    self.assertContains(response, "creates a new copy of it")

  def test_help_text_on_the_change_form(self):
    image = SystemImage.objects.create(name="compute", created_by=self.user)
    response = self.client.get(f"/admin/systems/systemimage/{image.pk}/change/")
    self.assertEqual(response.status_code, 200)
    self.assertContains(response, "creates a new copy of it")
