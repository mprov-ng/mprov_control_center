import importlib
import json

from django.apps import apps
from django.contrib.auth.models import User
from django.test import TestCase

from jobqueue.models import Job, JobModule, JobServer, JobStatus, filter_params
from systems.models import SystemImage

URL = "/admin/systems/systemimage/"


class MarkRebuildActionTests(TestCase):
  """ The "Rebuild selected images now" admin action queues one build of each
  selected image, the same as the "Rebuild now" button (#556). """

  def setUp(self):
    self.user = User.objects.create_superuser("admin", "admin@example.com", "password")
    self.client.force_login(self.user)
    JobStatus.objects.create(pk=1, name="PENDING")
    self.module = JobModule.objects.create(slug="image-update", name="Update Images")
    self.js1 = JobServer.objects.create(name="js1")
    self.images = []
    for name in ("compute", "login"):
      image = SystemImage.objects.create(name=name, created_by=self.user, needs_rebuild=False)
      image.jobservers.add(self.js1)
      self.images.append(SystemImage.objects.get(pk=image.pk))
    Job.objects.all().delete()

  def rebuild(self, images):
    return self.client.post(URL, {"action": "mark_rebuild", "_selected_action": [i.pk for i in images]}, follow=True)

  def jobs(self, image):
    return filter_params(Job.objects.filter(module=self.module), {"imageId": image.pk}).count()

  def test_each_image_gets_one_job_a_new_version_and_no_rebuild_flag(self):
    response = self.rebuild(self.images)
    self.assertEqual(response.status_code, 200)
    self.assertContains(response, "Queued a rebuild of")
    for before in self.images:
      image = SystemImage.objects.get(pk=before.pk)
      self.assertEqual(self.jobs(image), 1)
      self.assertEqual(image.version, before.version + 1)
      self.assertEqual(list(image.jobservers.all()), [])
      # still set, it made the next save of the image queue a second build.
      self.assertFalse(image.needs_rebuild)

  def test_the_job_server_registering_after_the_build_queues_nothing(self):
    self.rebuild(self.images[:1])
    image = SystemImage.objects.get(pk=self.images[0].pk)
    js2 = JobServer.objects.create(name="js2")
    # what the job server sends once the build is done.
    response = self.client.patch(f"/systemimages/{image.pk}/?addjs",
                                 json.dumps({"slug": image.pk, "jobservers": [js2.id], "version": image.version}),
                                 content_type="application/json")
    self.assertEqual(response.status_code, 200)
    image = SystemImage.objects.get(pk=image.pk)
    self.assertEqual(list(image.jobservers.values_list("id", flat=True)), [js2.id])
    self.assertEqual(self.jobs(image), 1)
    self.assertEqual(image.version, self.images[0].version + 1)

  def test_without_an_image_update_module_the_images_stay_marked(self):
    self.module.delete()
    response = self.rebuild(self.images)
    self.assertContains(response, "no rebuild was queued")
    self.assertEqual(Job.objects.count(), 0)
    for before in self.images:
      image = SystemImage.objects.get(pk=before.pk)
      self.assertTrue(image.needs_rebuild)
      self.assertEqual(image.version, before.version)


class ClearStaleNeedsRebuildMigrationTests(TestCase):
  """ The data migration clears the flag the old action left set, but only
  where an image-update module exists to have queued its build (#556). """

  def setUp(self):
    self.user = User.objects.create(username="migration-test")
    self.image = SystemImage.objects.create(name="compute", created_by=self.user, needs_rebuild=False)
    # as the old action left it: set without a save.
    SystemImage.objects.filter(pk=self.image.pk).update(needs_rebuild=True)
    migration = importlib.import_module("systems.migrations.0079_clear_stale_needs_rebuild")
    self.clear = migration.clear_stale_needs_rebuild

  def test_cleared_when_there_is_an_image_update_module(self):
    JobModule.objects.create(slug="image-update", name="Update Images")
    self.clear(apps, None)
    self.assertFalse(SystemImage.objects.get(pk=self.image.pk).needs_rebuild)

  def test_kept_when_there_is_no_image_update_module(self):
    self.clear(apps, None)
    self.assertTrue(SystemImage.objects.get(pk=self.image.pk).needs_rebuild)
