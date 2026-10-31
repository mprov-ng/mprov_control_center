from django.contrib import admin
from django.test import RequestFactory

from common.testing import APITestCase
from disklayouts.admin import DiskPartitionInline
from disklayouts.models import DiskLayout, RaidLayout


class AdminWizardTests(APITestCase):
  """ The add wizard (common.admin.AdminWizardModel) keeps its step, inlines
  and readonly fields per request, not on the shared ModelAdmin (#270). """

  add_url = "/admin/disklayouts/disklayout/add/"

  def setUp(self):
    super().setUp()
    self.model_admin = admin.site._registry[DiskLayout]

  def test_step_0_asks_only_for_the_type(self):
    page = self.client.get(self.add_url)
    self.assertEqual(page.status_code, 200)
    self.assertContains(page, 'name="dtype"')
    self.assertNotContains(page, 'name="name"')
    self.assertNotContains(page, 'name="partitions-TOTAL_FORMS"')
    self.assertContains(page, 'name="wizard_step" value="1"')
    # Software RAID has its own list.
    self.assertNotContains(page, 'value="mdrd"')

  def test_step_1_shows_the_rest_with_the_type_carried(self):
    page = self.client.post(self.add_url, {"dtype": "nvme", "wizard_step": "1"})
    self.assertEqual(page.status_code, 200)
    self.assertContains(page, 'name="name"')
    self.assertContains(page, 'name="diskname"')
    self.assertContains(page, '<input type="hidden" name="dtype" value="nvme"')

  def test_adding_saves_the_layout(self):
    response = self.client.post(self.add_url, {"dtype": "nvme", "wizard_step": "1", "name": "Compute disk",
                                               "diskname": "nvme0n1", "_continue": "1"})
    self.assertEqual(response.status_code, 302, response.content[:2000])
    layout = DiskLayout.objects.get(name="Compute disk")
    self.assertEqual((layout.dtype, layout.diskname), ("nvme", "nvme0n1"))

  def test_another_request_doesnt_leak_into_a_step(self):
    # someone opening a layout's edit page used to set the shared admin's
    # inlines, which the next person's step-1 add form then showed.
    layout = DiskLayout.objects.create(name="Edit me", diskname="sda", dtype="scsi")
    self.client.get(f"/admin/disklayouts/disklayout/{layout.pk}/change/")
    page = self.client.post(self.add_url, {"dtype": "nvme", "wizard_step": "1"})
    self.assertContains(page, 'name="name"')
    self.assertNotContains(page, 'name="partitions-TOTAL_FORMS"')
    # and a step-1 POST doesn't move the next person's add page on.
    self.assertNotContains(self.client.get(self.add_url), 'name="name"')

  def test_steps_of_two_requests_are_independent(self):
    factory = RequestFactory()
    mine = factory.post(self.add_url, {"wizard_step": "1"})
    theirs = factory.get(self.add_url)
    self.assertEqual(self.model_admin.wizard_step(mine), 1)
    self.assertEqual(self.model_admin.wizard_step(theirs), 0)
    self.assertEqual(self.model_admin.wizard_step(mine), 1)
    self.assertEqual(self.model_admin.wizard_step(factory.post(self.add_url, {"wizard_step": "x"})), 0)

  def test_edit_has_the_inlines_and_readonly_fields(self):
    layout = DiskLayout.objects.create(name="Edit me", diskname="sda", dtype="scsi")
    request = RequestFactory().get("/")
    request.user = self.user
    self.assertEqual(self.model_admin.get_inlines(request, layout), [DiskPartitionInline])
    self.assertEqual(list(self.model_admin.get_readonly_fields(request, layout)), ["dtype", "slug"])
    self.assertEqual(self.model_admin.get_inlines(request, None), [])
    page = self.client.get(f"/admin/disklayouts/disklayout/{layout.pk}/change/")
    self.assertEqual(page.status_code, 200)
    self.assertContains(page, 'name="partitions-TOTAL_FORMS"')

  def test_raid_layout_without_steps_is_the_normal_form(self):
    raid_admin = admin.site._registry[RaidLayout]
    request = RequestFactory().get("/")
    request.user = self.user
    self.assertEqual(list(raid_admin.get_readonly_fields(request, None)), ["dtype", "slug"])
    self.assertEqual(self.client.get("/admin/disklayouts/raidlayout/add/").status_code, 200)
