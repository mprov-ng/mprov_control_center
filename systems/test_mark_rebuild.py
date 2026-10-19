from django.contrib.auth.models import User
from django.test import TestCase

from systems.models import SystemImage


class MarkRebuildActionTests(TestCase):
  """ The "Mark images as needing rebuild" admin action handles every selected image and saves the new version. """

  def test_every_image_gets_a_job_and_a_new_version(self):
    from jobqueue.models import Job, JobModule, JobServer, JobStatus
    from systems.admin import mark_rebuild
    user = User.objects.create(username="rebuild-test")
    module = JobModule.objects.create(slug="image-update", name="Update Images")
    JobStatus.objects.create(pk=1, name="PENDING")
    jobserver = JobServer.objects.create(name="js1")
    images = []
    for name in ("compute", "login"):
      image = SystemImage.objects.create(name=name, created_by=user, needs_rebuild=False)
      image.jobservers.add(jobserver)
      images.append(image)
    versions = {image.pk: SystemImage.objects.get(pk=image.pk).version for image in images}
    Job.objects.all().delete()

    mark_rebuild(None, None, SystemImage.objects.all())

    for image in images:
      image = SystemImage.objects.get(pk=image.pk)
      self.assertTrue(image.needs_rebuild)
      self.assertEqual(image.version, versions[image.pk] + 1)
      self.assertEqual(list(image.jobservers.all()), [])
      self.assertEqual(Job.objects.filter(module=module, params__imageId=image.pk).count(), 1)
    self.assertEqual(SystemImage.objects.count(), 2)
