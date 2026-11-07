import json
import re

from django.contrib.auth.models import Permission, User
from django.test import TestCase

from systems.member_widget import CHIPS_SHOWN, lookup_systems
from systems.models import System, SystemGroup

LOOKUP = "/admin/systems/system/lookup/"


class MemberWidgetTests(TestCase):
  """ #497: the members of a System Group or Physical Disk Layout show as
  hostname chips; the IDs are still posted in one hidden field. """

  def setUp(self):
    self.user = User.objects.create_superuser("admin", "admin@example.com", "password")
    self.client.force_login(self.user)
    self.systems = [System.objects.create(hostname=f"c{i:03d}", created_by=self.user) for i in range(1, 61)]
    self.group = SystemGroup.objects.create(name="rack1")

  def page(self, url):
    response = self.client.get(url)
    self.assertEqual(response.status_code, 200)
    return response.content.decode()

  def members_json(self, html):
    match = re.search(r'<script id="id_systems_members" type="application/json">(.*?)</script>', html, re.S)
    self.assertIsNotNone(match)
    return json.loads(match.group(1))

  def test_group_shows_hostnames_with_a_hidden_id_field(self):
    self.group.systems.add(*self.systems[:3])
    html = self.page(f"/admin/systems/systemgroup/{self.group.pk}/change/")
    ids = ",".join(str(s.pk) for s in self.systems[:3])
    self.assertRegex(html, rf'<input type="hidden" name="systems" value="{ids}"[^>]*class="vManyToManyRawIdAdminField"')
    self.assertNotIn('type="text" name="systems"', html)
    # the row itself must show, though its input is hidden.
    self.assertIn('<div class="form-group field-systems">', html)
    self.assertNotIn('form-group hidden field-systems', html)
    for hostname in ("c001", "c002", "c003"):
      self.assertIn(f">{hostname}</span>", html)
    self.assertEqual([m["hostname"] for m in self.members_json(html)], ["c001", "c002", "c003"])
    self.assertIn("system_members.js", html)
    self.assertIn("Add many", html)
    self.assertIn(f'data-lookup-url="{LOOKUP}"', html)
    self.assertIn('id="lookup_id_systems"', html)

  def test_more_than_the_cap_shows_the_first_chips_and_a_count(self):
    self.group.systems.add(*self.systems)
    html = self.page(f"/admin/systems/systemgroup/{self.group.pk}/change/")
    self.assertEqual(html.count('class="system-member badge"'), CHIPS_SHOWN)
    self.assertIn(f"and {60 - CHIPS_SHOWN} more", html)
    self.assertEqual(len(self.members_json(html)), 60)

  def test_members_are_sorted_by_hostname_numbers_in_order(self):
    n10 = System.objects.create(hostname="n10", created_by=self.user)
    n2 = System.objects.create(hostname="n2", created_by=self.user)
    self.group.systems.add(n10, n2, self.systems[0])
    html = self.page(f"/admin/systems/systemgroup/{self.group.pk}/change/")
    self.assertEqual([m["hostname"] for m in self.members_json(html)], ["c001", "n2", "n10"])

  def test_saving_through_the_hidden_field(self):
    data = {"name": "rack1", "systems": f"{self.systems[0].pk},{self.systems[5].pk}", "install_kernel_cmdline": "",
            "tmpfs_root_size": 0, "initial_mods": "", "prov_interface": "", "config_params": "# Inherit from OS"}
    response = self.client.post(f"/admin/systems/systemgroup/{self.group.pk}/change/", data)
    self.assertEqual(response.status_code, 302)
    self.assertEqual(sorted(self.group.systems.values_list("hostname", flat=True)), ["c001", "c006"])

  def test_disk_layout_uses_the_same_widget(self):
    page = self.client.post("/admin/disklayouts/disklayout/add/", {"dtype": "nvme", "wizard_step": "1"})
    html = page.content.decode()
    self.assertIn('class="system-members"', html)
    self.assertIn('<input type="hidden" name="systems"', html)


class LookupViewTests(TestCase):
  """ #497: the admin lookup behind the chips and "Add many...". """

  def setUp(self):
    self.user = User.objects.create_superuser("admin", "admin@example.com", "password")
    self.client.force_login(self.user)
    self.c = {i: System.objects.create(hostname=f"c{i:03d}", created_by=self.user) for i in range(1, 6)}
    self.numeric = System.objects.create(hostname="4242", created_by=self.user)

  def post(self, **data):
    response = self.client.post(LOOKUP, data)
    self.assertEqual(response.status_code, 200)
    return response.json()

  def test_ids(self):
    data = self.post(ids=f"{self.c[2].pk},{self.c[1].pk},999999")
    self.assertEqual(data["found"], [{"id": self.c[2].pk, "hostname": "c002"}, {"id": self.c[1].pk, "hostname": "c001"}])
    self.assertEqual(data["not_found"], ["999999"])

  def test_pasted_hostnames_ids_and_ranges(self):
    text = f"c001, c003\nnope {self.c[5].pk}\tc[002-004] c[9-1]"
    data = self.post(text=text)
    self.assertEqual([m["hostname"] for m in data["found"]], ["c001", "c003", "c005", "c002", "c004"])
    self.assertEqual(len(data["not_found"]), 2)
    self.assertIn("nope", data["not_found"])
    self.assertTrue(any(e.startswith("c[9-1] (") for e in data["not_found"]))
    self.assertIsNone(data["error"])

  def test_a_number_that_isnt_an_id_is_tried_as_a_hostname(self):
    self.assertEqual(self.post(text="4242")["found"], [{"id": self.numeric.pk, "hostname": "4242"}])

  def test_too_many_is_refused(self):
    data = self.post(text=" ".join(f"x[0001-1000]{n}" for n in range(11)))
    self.assertIn("smaller batches", data["error"])
    self.assertEqual(data["found"], [])

  def test_more_names_than_one_query_can_take(self):
    System.objects.bulk_create([System(hostname=f"big{i:04d}", created_by=self.user) for i in range(1000)])
    data = lookup_systems(text="big[0000-0999]")
    self.assertEqual(len(data["found"]), 1000)

  def test_get_is_not_allowed(self):
    self.assertEqual(self.client.get(LOOKUP).status_code, 405)

  def test_needs_view_permission_on_systems(self):
    staff = User.objects.create_user("staff", password="x", is_staff=True)
    self.client.force_login(staff)
    self.assertEqual(self.client.post(LOOKUP, {"ids": "1"}).status_code, 403)
    staff.user_permissions.add(Permission.objects.get(codename="view_system"))
    self.client.force_login(User.objects.get(pk=staff.pk))
    self.assertEqual(self.client.post(LOOKUP, {"ids": str(self.c[1].pk)}).status_code, 200)
