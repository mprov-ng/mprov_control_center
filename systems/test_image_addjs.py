from django.contrib.auth.models import User
from django.test import TestCase

from systems.models import SystemImage


class SystemImageAddJobserverTests(TestCase):
  """ PATCH /systemimages/<pk>/?addjs adds job servers to the image instead of replacing them. """

  def setUp(self):
    from jobqueue.models import JobServer
    self.user = User.objects.create_superuser("admin", "admin@example.com", "password")
    self.client.force_login(self.user)
    self.image = SystemImage.objects.create(name="compute", created_by=self.user, needs_rebuild=False)
    self.js1, self.js2, self.js3 = (JobServer.objects.create(name=f"js{i}") for i in range(1, 4))
    self.image.jobservers.add(self.js1)

  def addjs(self, jobservers):
    import json
    return self.client.patch(f"/systemimages/{self.image.pk}/?addjs", json.dumps({"jobservers": jobservers}),
                             content_type="application/json")

  def jobserver_ids(self):
    return sorted(self.image.jobservers.values_list("id", flat=True))

  def test_add_a_list(self):
    self.assertEqual(self.addjs([self.js2.id, self.js3.id]).status_code, 200)
    self.assertEqual(self.jobserver_ids(), [self.js1.id, self.js2.id, self.js3.id])

  def test_add_one(self):
    self.assertEqual(self.addjs(self.js2.id).status_code, 200)
    self.assertEqual(self.jobserver_ids(), [self.js1.id, self.js2.id])

  def test_unknown_image_is_404(self):
    # issue #324: was a 500 from DoesNotExist.
    import json
    response = self.client.patch("/systemimages/nope/?addjs", json.dumps({"jobservers": [self.js2.id]}),
                                 content_type="application/json")
    self.assertEqual(response.status_code, 404)


class SystemImageAddJobserverVersionTests(TestCase):
  """ Issue #396: ?addjs with a "version" only adds hosts of the image's current version. """

  def setUp(self):
    from jobqueue.models import JobServer
    self.user = User.objects.create_superuser("admin", "admin@example.com", "password")
    self.client.force_login(self.user)
    self.image = SystemImage.objects.create(name="compute", created_by=self.user, needs_rebuild=False)
    self.js1, self.js2 = (JobServer.objects.create(name=f"js{i}") for i in range(1, 3))
    self.image.jobservers.add(self.js1)
    self.image.refresh_from_db()

  def addjs(self, data):
    import json
    return self.client.patch(f"/systemimages/{self.image.pk}/?addjs", json.dumps(data), content_type="application/json")

  def jobserver_ids(self):
    return sorted(self.image.jobservers.values_list("id", flat=True))

  def test_current_version_adds(self):
    version = self.image.version
    response = self.addjs({"jobservers": [self.js2.id], "version": version})
    self.assertEqual(response.status_code, 200)
    self.assertEqual(self.jobserver_ids(), [self.js1.id, self.js2.id])
    self.image.refresh_from_db()
    self.assertEqual(self.image.version, version)

  def test_version_as_a_string_is_accepted(self):
    response = self.addjs({"jobservers": [self.js2.id], "version": str(self.image.version)})
    self.assertEqual(response.status_code, 200)
    self.assertEqual(self.jobserver_ids(), [self.js1.id, self.js2.id])

  def test_stale_version_is_409_and_changes_nothing(self):
    version = self.image.version
    response = self.addjs({"jobservers": [self.js2.id], "version": version - 1, "needs_rebuild": True})
    self.assertEqual(response.status_code, 409)
    self.assertEqual(response.json()["version"], version)
    self.assertEqual(self.jobserver_ids(), [self.js1.id])
    self.image.refresh_from_db()
    self.assertEqual(self.image.version, version)
    self.assertFalse(self.image.needs_rebuild)

  def test_non_integer_version_is_400(self):
    response = self.addjs({"jobservers": [self.js2.id], "version": "latest"})
    self.assertEqual(response.status_code, 400)
    self.assertEqual(self.jobserver_ids(), [self.js1.id])

  def test_without_version_merges_as_before(self):
    response = self.addjs({"jobservers": [self.js2.id]})
    self.assertEqual(response.status_code, 200)
    self.assertEqual(self.jobserver_ids(), [self.js1.id, self.js2.id])

  def test_rebuild_between_get_and_addjs(self):
    """ The race in #396: the job server read the old version, then the image was rebuilt. """
    from jobqueue.models import JobModule, JobStatus
    JobModule.objects.create(slug="image-update", name="Update Images")
    JobStatus.objects.get_or_create(pk=1, defaults={"name": "PENDING"})
    # what the job server's GET returned.
    seen = {"version": self.image.version, "jobservers": self.jobserver_ids()}
    # the rebuild bumps the version and clears every host.
    self.image.needs_rebuild = True
    self.image.save()
    self.image.refresh_from_db()
    self.assertEqual(self.image.version, seen["version"] + 1)
    self.assertEqual(self.jobserver_ids(), [])

    response = self.addjs({"jobservers": seen["jobservers"] + [self.js2.id], "version": seen["version"]})
    self.assertEqual(response.status_code, 409)
    self.assertEqual(response.json()["version"], seen["version"] + 1)
    # neither the caller nor the old host comes back.
    self.assertEqual(self.jobserver_ids(), [])
