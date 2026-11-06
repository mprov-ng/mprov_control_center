from django.contrib import admin
from django.contrib.messages import get_messages
from django.test import TestCase

from common.testing import APITestCase
from jobqueue.models import Job, JobModule, JobServer, JobStatus, filter_params
from systems.models import System, SystemGroup, SystemImage, SystemModel


def change_url(obj):
  return f"/admin/systems/{obj._meta.model_name}/{obj.pk}/change/"


class ImageRebuildNowTests(APITestCase):
  """ #176: the "Rebuild now" button on an image's change page saves the
  form and queues exactly one rebuild, through the same pre_save signal as
  ticking "Rebuild Image?". """

  def setUp(self):
    super().setUp()
    self.module = JobModule.objects.create(slug="image-update", name="Update Images")
    JobStatus.objects.get_or_create(pk=1, defaults={"name": "PENDING"})
    self.jobserver = JobServer.objects.create(name="js1")
    self.image = SystemImage.objects.create(name="compute", created_by=self.user, needs_rebuild=False)
    self.image.jobservers.add(self.jobserver)
    self.version = SystemImage.objects.get(pk=self.image.pk).version
    Job.objects.all().delete()

  def form_data(self, **changes):
    # the change form as it stands, so the POST carries every field
    form = self.client.get(change_url(self.image)).context["adminform"].form
    data = {}
    for name, field in form.fields.items():
      value = form[name].value()
      if value is None:
        continue
      if isinstance(value, (list, tuple)):
        data[name] = [str(v) for v in value]
      elif isinstance(value, bool):
        if value:
          data[name] = "on"
      else:
        data[name] = value
    data.update(changes)
    return data

  def jobs(self):
    return filter_params(Job.objects.filter(module=self.module), {"imageId": self.image.pk})

  def test_the_button_is_on_the_change_page_but_not_the_add_page(self):
    self.assertContains(self.client.get(change_url(self.image)), 'name="_rebuild_now"')
    self.assertNotContains(self.client.get("/admin/systems/systemimage/add/"), 'name="_rebuild_now"')

  def test_rebuild_now_queues_one_job_and_bumps_the_version(self):
    response = self.client.post(change_url(self.image), self.form_data(_rebuild_now="Rebuild now"))
    self.assertRedirects(response, change_url(self.image), fetch_redirect_response=False)
    image = SystemImage.objects.get(pk=self.image.pk)
    self.assertEqual(self.jobs().count(), 1)
    self.assertEqual(image.version, self.version + 1)
    self.assertFalse(image.needs_rebuild)
    self.assertEqual(list(image.jobservers.all()), [])
    self.assertIn(f"Queued a rebuild of compute (version {image.version}).",
                  [str(m) for m in get_messages(response.wsgi_request)])

  def test_ticking_the_box_as_well_still_queues_one_job(self):
    self.client.post(change_url(self.image), self.form_data(needs_rebuild="on", _rebuild_now="Rebuild now"))
    self.assertEqual(self.jobs().count(), 1)
    self.assertEqual(SystemImage.objects.get(pk=self.image.pk).version, self.version + 1)

  def test_other_edits_in_the_form_are_saved_too(self):
    self.client.post(change_url(self.image), self.form_data(customIPXE="#!ipxe\necho hi", _rebuild_now="Rebuild now"))
    self.assertEqual(SystemImage.objects.get(pk=self.image.pk).customIPXE.replace("\r\n", "\n"), "#!ipxe\necho hi")
    self.assertEqual(self.jobs().count(), 1)

  def test_a_plain_save_queues_nothing(self):
    response = self.client.post(change_url(self.image), self.form_data(_save="Save"))
    self.assertEqual(response.status_code, 302)
    self.assertEqual(self.jobs().count(), 0)
    self.assertEqual(SystemImage.objects.get(pk=self.image.pk).version, self.version)

  def test_without_an_image_update_module_it_says_nothing_was_queued(self):
    self.module.delete()
    response = self.client.post(change_url(self.image), self.form_data(_rebuild_now="Rebuild now"))
    self.assertEqual(Job.objects.count(), 0)
    self.assertTrue(SystemImage.objects.get(pk=self.image.pk).needs_rebuild)
    self.assertTrue(any("no rebuild was queued" in str(m) for m in get_messages(response.wsgi_request)))


class SystemsSubmitButtonsTests(APITestCase):
  """ #479: "Copy to new" is only on System's change page, the only systems
  admin that handles it; "Rebuild now" (#176) is only on SystemImage's. """

  def test_each_button_is_only_on_its_own_models_page(self):
    objects = [
      System.objects.create(hostname="node01", created_by=self.user),
      SystemImage.objects.create(name="login", created_by=self.user, needs_rebuild=False),
      SystemGroup.objects.create(name="group1"),
      SystemModel.objects.create(name="model1", vendor="vendor1"),
    ]
    expected = {System: "_copy_to_new", SystemImage: "_rebuild_now"}
    for obj in objects:
      with self.subTest(obj._meta.model_name):
        page = self.client.get(change_url(obj)).content.decode()
        for model, button in expected.items():
          self.assertEqual(f'name="{button}"' in page, type(obj) is model, button)


class RebuildActionNameTests(TestCase):
  """ #176: the changelist action already queues the rebuild, so it says so. """

  def test_the_action_says_it_rebuilds_now(self):
    from systems.admin import mark_rebuild
    self.assertIn(mark_rebuild, admin.site._registry[SystemImage].actions)
    self.assertEqual(mark_rebuild.short_description, "Rebuild selected images now")
