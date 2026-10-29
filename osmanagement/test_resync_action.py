from django.test import TestCase

from jobqueue.models import Job, JobModule, JobServer, JobStatus
from osmanagement.admin import resync_repos
from osmanagement.models import OSRepo


class RepoJobTestCase(TestCase):

  def setUp(self):
    self.module = JobModule.objects.create(slug="repo-update", name="Update Repos")
    JobStatus.objects.create(pk=1, name="PENDING")
    JobStatus.objects.create(pk=2, name="RUNNING")


class ResyncActionTests(RepoJobTestCase):
  """ The admin's "Re-sync" action handles every selected managed repo and saves the new version. """

  def test_every_repo_gets_a_job_and_a_new_version(self):
    repos = [OSRepo.objects.create(name=f"repo{i}", repo_package_url="http://mirror/", managed=True) for i in range(2)]
    resync_repos(None, None, OSRepo.objects.all())
    for repo in repos:
      repo.refresh_from_db()
      self.assertFalse(repo.resync)
      self.assertEqual(repo.version, 2)
      self.assertEqual(Job.objects.filter(module=self.module, params={"repo_id": repo.id}).count(), 1)

  def test_unmanaged_repo_is_left_alone(self):
    jobserver = JobServer.objects.create(name="js1")
    repo = OSRepo.objects.create(name="external", repo_package_url="http://mirror/")
    repo.hosted_by.add(jobserver)
    resync_repos(None, None, OSRepo.objects.all())
    repo.refresh_from_db()
    self.assertFalse(repo.resync)
    self.assertEqual(repo.version, 1)
    self.assertEqual(list(repo.hosted_by.all()), [jobserver])
    self.assertFalse(Job.objects.exists())
