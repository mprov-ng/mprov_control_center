from django.test import TestCase
from rest_framework_api_key.models import APIKey

from networks.models import Network, NetworkType


class NetworkFunctionViewPermissionTests(TestCase):
  """ Issue #272: the @api_view network endpoints take a login OR the API key, like MProvView. """

  def setUp(self):
    net_type = NetworkType.objects.create(name="Ethernet")
    self.lan = Network.objects.create(name="Cluster LAN", net_type=net_type, subnet="172.16.0.0", netmask=16)
    _, self.key = APIKey.objects.create_key(name="jobserver")

  def preview(self, **extra):
    return self.client.get(f"/networks/{self.lan.pk}/preview-subnet-changes/?new_subnet=172.17.0.0&new_netmask=16", **extra)

  def update(self, **extra):
    return self.client.post(f"/networks/{self.lan.pk}/update-with-confirmation/", '{"network_data": {"domain": "perm-test"}}',
                            content_type="application/json", **extra)

  def test_api_key_alone_is_enough(self):
    self.assertEqual(self.preview(HTTP_AUTHORIZATION=f"Api-Key {self.key}").status_code, 200)
    self.assertEqual(self.update(HTTP_AUTHORIZATION=f"Api-Key {self.key}").status_code, 200)

  def test_login_alone_is_enough(self):
    from django.contrib.auth.models import User
    self.client.force_login(User.objects.create_superuser("admin", "admin@example.com", "password"))
    self.assertEqual(self.preview().status_code, 200)
    self.assertEqual(self.update().status_code, 200)

  def test_neither_is_refused(self):
    self.assertIn(self.preview().status_code, (401, 403))
    self.assertIn(self.update().status_code, (401, 403))
    self.assertIn(self.preview(HTTP_AUTHORIZATION="Api-Key not-a-key").status_code, (401, 403))
    self.lan.refresh_from_db()
    self.assertNotEqual(self.lan.domain, "perm-test")
