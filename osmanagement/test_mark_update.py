from django.test import TestCase

from jobqueue.models import Job, JobModule, JobStatus
from osmanagement.admin import mark_update
from osmanagement.models import OSRepo


class RepoJobTestCase(TestCase):

  def setUp(self):
    self.module = JobModule.objects.create(slug="repo-update", name="Update Repos")
    JobStatus.objects.create(pk=1, name="PENDING")
    JobStatus.objects.create(pk=2, name="RUNNING")


class MarkUpdateActionTests(RepoJobTestCase):
  """ The admin's "mark as needing update" action handles every selected repo and saves the new version. """

  def test_every_repo_gets_a_job_and_a_new_version(self):
    repos = [OSRepo.objects.create(name=f"repo{i}", repo_package_url="http://mirror/") for i in range(2)]
    mark_update(None, None, OSRepo.objects.all())
    for repo in repos:
      repo.refresh_from_db()
      self.assertTrue(repo.update)
      self.assertEqual(repo.version, 2)
      self.assertEqual(Job.objects.filter(module=self.module, params={"repo_id": repo.id}).count(), 1)
