from django.contrib.auth.models import User
from django.test import TestCase

from networks.models import Switch
from systems.models import System, SystemImage


class CreatedByUpdatedByTests(TestCase):
  """ #493: created_by is who created an object and is set only then;
  updated_by is who saved it last.  Both are set from the request, and the
  API can't write either. """

  def setUp(self):
    self.alice = User.objects.create_superuser("alice", "alice@example.com", "password")
    self.bob = User.objects.create_superuser("bob", "bob@example.com", "password")
    self.carol = User.objects.create_superuser("carol", "carol@example.com", "password")

  def as_user(self, user):
    self.client.force_login(user)

  def post(self, url, data):
    return self.client.post(url, data, content_type="application/json")

  def patch(self, url, data):
    return self.client.patch(url, data, content_type="application/json")

  def test_system_created_then_edited_by_someone_else(self):
    self.as_user(self.alice)
    response = self.post("/systems/", {"hostname": "c01"})
    self.assertIn(response.status_code, (200, 201), response.content)
    system = System.objects.get(hostname="c01")
    self.assertEqual((system.created_by, system.updated_by), (self.alice, self.alice))

    self.as_user(self.bob)
    response = self.patch(f"/systems/{system.pk}/", {"hostname": "c01-renamed"})
    self.assertEqual(response.status_code, 200, response.content)
    system.refresh_from_db()
    self.assertEqual((system.created_by, system.updated_by), (self.alice, self.bob))
    self.assertEqual(response.json()["created_by"], self.alice.pk)
    self.assertEqual(response.json()["updated_by"], self.bob.pk)

  def test_the_api_cant_write_created_by_or_updated_by(self):
    self.as_user(self.alice)
    system = System.objects.create(hostname="c01", created_by=self.alice)
    self.as_user(self.bob)
    response = self.patch(f"/systems/{system.pk}/", {"created_by": self.carol.pk, "updated_by": self.carol.pk})
    self.assertEqual(response.status_code, 200, response.content)
    system.refresh_from_db()
    self.assertEqual(system.created_by, self.alice)
    self.assertEqual(system.updated_by, self.bob)

  def test_a_create_that_sends_created_by_gets_the_acting_user(self):
    # mprov_scripts' mash tools send created_by=1; it's ignored now.
    self.as_user(self.bob)
    response = self.post("/systems/", {"hostname": "c02", "created_by": self.carol.pk})
    self.assertIn(response.status_code, (200, 201), response.content)
    self.assertEqual(System.objects.get(hostname="c02").created_by, self.bob)

  def test_system_image(self):
    image = SystemImage.objects.create(name="compute", created_by=self.alice, needs_rebuild=False)
    self.as_user(self.bob)
    response = self.patch(f"/systemimages/{image.slug}/", {"version": 2})
    self.assertEqual(response.status_code, 200, response.content)
    image.refresh_from_db()
    self.assertEqual((image.created_by, image.updated_by), (self.alice, self.bob))

  def test_switch(self):
    switch = Switch.objects.create(hostname="sw1", mgmt_ip="10.0.0.250", mgmt_mac="de:ad:be:ef:00:01",
                                   created_by=self.alice)
    self.as_user(self.bob)
    response = self.patch(f"/switches/{switch.pk}/", {"hostname": "sw1b"})
    self.assertEqual(response.status_code, 200, response.content)
    switch.refresh_from_db()
    self.assertEqual((switch.created_by, switch.updated_by), (self.alice, self.bob))

  def test_a_save_outside_a_request_changes_neither(self):
    system = System.objects.create(hostname="c01", created_by=self.alice)
    system.hostname = "c01b"
    system.save()
    system.refresh_from_db()
    self.assertEqual(system.created_by, self.alice)
    self.assertIsNone(system.updated_by)

  def test_admin_shows_both(self):
    system = System.objects.create(hostname="c01", created_by=self.alice)
    self.as_user(self.bob)
    page = self.client.get(f"/admin/systems/system/{system.pk}/change/")
    self.assertContains(page, "Created By")
    self.assertContains(page, "Updated By")
