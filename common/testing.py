from django.contrib.auth.models import User
from django.test import TestCase


class APITestCase(TestCase):
  """ Logs in as a superuser and sends JSON, so the API views return data instead of their docs page. """

  def setUp(self):
    self.user = User.objects.create_superuser("admin", "admin@example.com", "password")
    self.client.force_login(self.user)

  def get_json(self, url):
    return self.client.get(url, CONTENT_TYPE="application/json")
