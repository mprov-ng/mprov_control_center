import json

from django.contrib.auth.models import User
from django.test import TestCase

from jobqueue.models import Job, JobModule, JobServer, JobStatus
from osmanagement.models import OSDistro, OSRepo

RUNNING, ERROR, COMPLETE = 2, 3, 4


class RepoResyncTests(TestCase):
  """ resync is one-shot: one save queues one re-sync, and later saves of the repo don't (#358). """

  def setUp(self):
    self.module = JobModule.objects.create(slug="repo-update", name="Update Repos")
    for pk, name in ((1, "PENDING"), (RUNNING, "RUNNING"), (ERROR, "ERROR"), (COMPLETE, "COMPLETE")):
      JobStatus.objects.create(pk=pk, name=name)
    self.js1 = JobServer.objects.create(name="js1")
    self.js2 = JobServer.objects.create(name="js2")
    self.client.force_login(User.objects.create_superuser("admin", "admin@example.com", "password"))
    self.repo = OSRepo.objects.create(name="BaseOS", repo_package_url="http://mirror/", managed=True, resync=True)

  def jobs(self):
    return Job.objects.filter(module=self.module, params={"repo_id": self.repo.id}).count()

  def patch(self, data):
    response = self.client.patch(f"/repos/{self.repo.id}/", json.dumps(data), content_type="application/json")
    self.assertEqual(response.status_code, 200, response.content)
    self.repo.refresh_from_db()
    return response.json()

  def assertSyncedOnce(self):
    self.assertEqual(self.jobs(), 1)
    self.assertEqual(self.repo.version, 2)
    self.assertFalse(self.repo.resync)

  def test_save_queues_a_sync_and_clears_resync(self):
    self.repo.refresh_from_db()
    self.assertSyncedOnce()

  def test_job_server_patch_during_the_sync_does_not_resync(self):
    # repo_sync on another job server adds itself to hosted_by.
    Job.objects.update(status=RUNNING)
    self.patch({"id": self.repo.id, "hosted_by": [self.js2.id]})
    self.assertSyncedOnce()
    self.assertEqual(list(self.repo.hosted_by.all()), [self.js2])

  def test_edit_after_a_failed_sync_does_not_resync(self):
    Job.objects.update(status=ERROR)
    self.patch({"id": self.repo.id, "name": "BaseOS renamed"})
    self.assertSyncedOnce()

  def test_old_job_server_patch_still_works(self):
    # Job servers before mprov_jobserver#204 also send update: false.
    Job.objects.update(status=COMPLETE)
    self.patch({"id": self.repo.id, "hosted_by": [self.js1.id], "update": False})
    self.assertSyncedOnce()
    self.assertEqual(list(self.repo.hosted_by.all()), [self.js1])

  def test_api_resync_reads_back_false(self):
    Job.objects.update(status=COMPLETE)
    body = self.patch({"id": self.repo.id, "resync": True})
    self.assertFalse(body["resync"])
    self.assertNotIn("update", body)
    self.assertEqual(self.jobs(), 2)
    self.assertEqual(self.repo.version, 3)

  def test_unmanaged_repo_resync_is_cleared_without_a_job(self):
    repo = OSRepo.objects.create(name="external", repo_package_url="http://mirror/", resync=True)
    repo.refresh_from_db()
    self.assertFalse(repo.resync)
    self.assertEqual(repo.version, 1)
    self.assertFalse(Job.objects.filter(params={"repo_id": repo.id}).exists())


class DistroRegenerateResyncTests(TestCase):
  """ Regenerating a distro's repos only re-syncs the ones that are new, moved or newly mirrored. """

  def setUp(self):
    self.module = JobModule.objects.create(slug="repo-update", name="Update Repos")
    for pk, name in ((1, "PENDING"), (COMPLETE, "COMPLETE")):
      JobStatus.objects.create(pk=pk, name=name)

  def regenerate(self, distro, **fields):
    Job.objects.update(status=COMPLETE)
    for name, value in fields.items():
      setattr(distro, name, value)
    distro.update = True
    distro.save()

  def test_unchanged_repos_are_not_resynced(self):
    distro = OSDistro.objects.create(name="R8", vendor="R", version="8", update=True, managed=True, baseurl="http://m/8")
    self.assertEqual(Job.objects.count(), 5)
    self.regenerate(distro)
    self.assertEqual(Job.objects.count(), 5)
    self.assertEqual(set(OSRepo.objects.values_list("version", flat=True)), {2})

  def test_moved_repos_are_resynced(self):
    distro = OSDistro.objects.create(name="R8", vendor="R", version="8", update=True, managed=True, baseurl="http://m/8")
    self.regenerate(distro, baseurl="http://other/8")
    # EPEL's URL doesn't come from baseurl.
    self.assertEqual(Job.objects.count(), 9)
    self.assertEqual(OSRepo.objects.get(name="EPEL-8").version, 2)
    self.assertEqual(OSRepo.objects.get(name="BaseOS-8").version, 3)

  def test_newly_mirrored_repos_are_synced(self):
    distro = OSDistro.objects.create(name="R8", vendor="R", version="8", update=True, baseurl="http://m/8")
    self.assertFalse(Job.objects.exists())
    self.regenerate(distro, managed=True)
    self.assertEqual(Job.objects.count(), 5)
    self.assertFalse(OSRepo.objects.filter(resync=True).exists())
