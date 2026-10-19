from django.test import TestCase

from jobqueue.models import Job, JobModule, JobServer, JobStatus
from osmanagement.models import OSRepo


class RepoJobTestCase(TestCase):

  def setUp(self):
    self.module = JobModule.objects.create(slug="repo-update", name="Update Repos")
    JobStatus.objects.create(pk=1, name="PENDING")
    JobStatus.objects.create(pk=2, name="RUNNING")


class RepoUpdateJobTests(RepoJobTestCase):
  """ Repo-update jobs aren't queued twice for the same repo while one is pending. """

  def test_saving_a_repo_twice_queues_one_job(self):
    repo = OSRepo.objects.create(name="BaseOS", repo_package_url="http://mirror/", managed=True, update=True)
    repo.save()
    self.assertEqual(Job.objects.filter(module=self.module, params={"repo_id": repo.id}).count(), 1)

  def test_new_job_once_the_old_one_is_running(self):
    repo = OSRepo.objects.create(name="BaseOS", repo_package_url="http://mirror/", managed=True, update=True)
    Job.objects.update(status=2)
    repo.save()
    self.assertEqual(Job.objects.filter(module=self.module, params={"repo_id": repo.id}).count(), 2)

  def test_deleting_job_servers_queues_one_job_per_repo(self):
    repos = [OSRepo.objects.create(name=f"repo{i}", repo_package_url="http://mirror/") for i in range(2)]
    for i in range(3):
      JobServer.objects.create(name=f"js{i}")
    JobServer.objects.all().delete()
    for repo in repos:
      self.assertEqual(Job.objects.filter(module=self.module, params={"repo_id": repo.id}).count(), 1)
