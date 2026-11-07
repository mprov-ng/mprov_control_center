from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from rest_framework_api_key.models import APIKey

LIST = "/admin/rest_framework_api_key/apikey/"


class LegacyAPIKeyAdminTests(TestCase):
  """ #500: the API Keys pages say the shared key is legacy, in words that
  follow MPROV_SHARED_KEY_MODE; adding a key still works. """

  def setUp(self):
    self.client.force_login(User.objects.create_superuser("admin", "admin@example.com", "password"))
    self.key, _ = APIKey.objects.create_key(name="old key")

  def pages(self):
    return [LIST, LIST + "add/", f"{LIST}{self.key.pk}/change/"]

  def banners(self, url):
    response = self.client.get(url)
    self.assertEqual(response.status_code, 200)
    return [str(m) for m in response.context["messages"]]

  @override_settings(MPROV_SHARED_KEY_MODE="all")
  def test_all(self):
    for url in self.pages():
      [banner] = self.banners(url)
      self.assertIn("Legacy: API keys are deprecated.", banner)
      self.assertIn("(now: all, accepted everywhere)", banner)
      self.assertIn("removed in 0.8.0", banner)
      self.assertIn("Agent Identities", banner)

  @override_settings(MPROV_SHARED_KEY_MODE="nodes")
  def test_nodes(self):
    for url in self.pages():
      [banner] = self.banners(url)
      self.assertIn("(now: nodes, accepted only for what a node does to itself)", banner)

  @override_settings(MPROV_SHARED_KEY_MODE="off")
  def test_off(self):
    for url in self.pages():
      self.assertEqual(self.banners(url),
                       ["API keys are not accepted (MPROV_SHARED_KEY_MODE=off) and are removed in 0.8.0."])

  def test_banner_shows_on_the_page(self):
    self.assertContains(self.client.get(LIST), "removed in 0.8.0")

  @override_settings(MPROV_SHARED_KEY_MODE="all")
  def test_adding_a_key_still_works(self):
    response = self.client.post(LIST + "add/", {"name": "rotated", "expiry_date_0": "", "expiry_date_1": ""}, follow=True)
    self.assertEqual(response.status_code, 200)
    self.assertTrue(APIKey.objects.filter(name="rotated").exists())
    shown = [str(m) for m in response.context["messages"]]
    self.assertTrue(any("The API key for rotated is:" in m for m in shown), shown)
    # the redirect target warns once, not once per request in the chain.
    self.assertEqual(sum("removed in 0.8.0" in m for m in shown), 1)
