from django.test import TestCase


class ImagesAPIViewTests(TestCase):
  """ /images/<pk>/ redirects to a job server hosting the image, or 404s. """

  def test_unknown_image_is_404(self):
    self.assertEqual(self.client.get("/images/nope/").status_code, 404)
    self.assertEqual(self.client.get("/images/nope.vmlinuz/").status_code, 404)
