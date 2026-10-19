from django.contrib.auth.models import User
from django.test import TestCase

from systems.models import System, SystemGroup


class SystemAPIViewListTests(TestCase):
  """ GET /systems/ applies ?FIELD= filters together with ?hostname=, and keeps the base class's responses. """

  def setUp(self):
    self.user = User.objects.create_superuser("admin", "admin@example.com", "password")
    self.client.force_login(self.user)
    self.group = SystemGroup.objects.create(name="compute")
    for hostname in ("compute001", "compute002", "login001"):
      System.objects.create(hostname=hostname, created_by=self.user)
    System.objects.get(hostname="compute002").systemgroups.add(self.group)

  def get_json(self, url):
    return self.client.get(url, CONTENT_TYPE="application/json")

  def hostnames(self, response):
    self.assertEqual(response.status_code, 200)
    return sorted(s["hostname"] for s in response.json())

  def test_hostname_contains(self):
    self.assertEqual(self.hostnames(self.get_json("/systems/?hostname=compute")), ["compute001", "compute002"])

  def test_hostname_keeps_other_filters(self):
    response = self.get_json(f"/systems/?hostname=compute&systemgroups={self.group.pk}")
    self.assertEqual(self.hostnames(response), ["compute002"])

  def test_unknown_hostname_is_404(self):
    self.assertEqual(self.get_json("/systems/?hostname=nope").status_code, 404)

  def test_bad_filter_is_400(self):
    response = self.get_json("/systems/?systemgroups=not-a-number")
    self.assertEqual(response.status_code, 400)
    self.assertIn("systemgroups", response.json())

  def test_no_matches_is_an_empty_list(self):
    # libgenders in the jobserver fails its job on a 404 here.
    self.assertEqual(self.hostnames(self.get_json("/systems/?systemgroups=999")), [])

  def test_docs_page(self):
    response = self.client.get("/systems/")
    self.assertTrue(response["Content-Type"].startswith("text/html"))
    self.assertIn("<h1>/systems/</h1>", response.content.decode())
