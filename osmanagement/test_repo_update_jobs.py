import datetime

from django.test import TestCase, override_settings
from django.utils import timezone

from jobqueue.models import Job, JobModule, JobServer, JobStatus, sweep_stale_jobservers
from osmanagement.models import OSRepo


class RepoJobTestCase(TestCase):

  def setUp(self):
    self.module = JobModule.objects.create(slug="repo-update", name="Update Repos")
    JobStatus.objects.create(pk=1, name="PENDING")
    JobStatus.objects.create(pk=2, name="RUNNING")


class RepoUpdateJobTests(RepoJobTestCase):
  """ Repo-update jobs aren't queued twice for the same repo while one is pending. """

  def test_saving_a_repo_twice_queues_one_job(self):
    repo = OSRepo.objects.create(name="BaseOS", repo_package_url="http://mirror/", managed=True, resync=True)
    repo.save()
    self.assertEqual(Job.objects.filter(module=self.module, params={"repo_id": repo.id}).count(), 1)

  def test_new_job_once_the_old_one_is_running(self):
    repo = OSRepo.objects.create(name="BaseOS", repo_package_url="http://mirror/", managed=True, resync=True)
    Job.objects.update(status=2)
    repo.resync = True
    repo.save()
    self.assertEqual(Job.objects.filter(module=self.module, params={"repo_id": repo.id}).count(), 2)

  def test_deleting_job_servers_queues_one_job_per_repo(self):
    servers = [JobServer.objects.create(name=f"js{i}") for i in range(3)]
    repos = [OSRepo.objects.create(name=f"repo{i}", repo_package_url="http://mirror/", managed=True) for i in range(2)]
    for repo in repos:
      repo.hosted_by.set(servers)
    JobServer.objects.all().delete()
    for repo in repos:
      self.assertEqual(Job.objects.filter(module=self.module, params={"repo_id": repo.id}).count(), 1)


class DeleteJobServerRepoTests(RepoJobTestCase):
  """ Deleting a job server queues a repo-update only for the mirrored repos
  it hosted that no other job server hosts, so they're mirrored again
  somewhere.  It used to queue every repo, mirrored or not (#463). """

  def setUp(self):
    super().setUp()
    self.server = JobServer.objects.create(name="js-gone")
    self.other = JobServer.objects.create(name="js-other")

  def repo(self, name, managed=True, hosts=()):
    repo = OSRepo.objects.create(name=name, repo_package_url="http://mirror/", managed=managed)
    repo.hosted_by.set(hosts)
    return repo

  def jobs_for(self, repo):
    return Job.objects.filter(module=self.module, params={"repo_id": repo.id}).count()

  def test_unmanaged_repo_isnt_queued(self):
    repo = self.repo("upstream", managed=False, hosts=[self.server])
    self.server.delete()
    self.assertEqual(self.jobs_for(repo), 0)

  def test_repo_left_with_no_host_is_queued(self):
    repo = self.repo("mirror", hosts=[self.server])
    self.server.delete()
    self.assertEqual(self.jobs_for(repo), 1)

  def test_repo_still_hosted_elsewhere_isnt_queued(self):
    repo = self.repo("mirror", hosts=[self.server, self.other])
    self.server.delete()
    self.assertEqual(self.jobs_for(repo), 0)

  def test_repo_the_server_didnt_host_isnt_queued(self):
    repo = self.repo("mirror", hosts=[self.other])
    self.server.delete()
    self.assertEqual(self.jobs_for(repo), 0)

  def test_repo_whose_hosts_are_deleted_together_is_queued(self):
    # a bulk delete (the admin's "delete selected") runs every pre_delete
    # before deleting any of them.
    repo = self.repo("mirror", hosts=[self.server, self.other])
    JobServer.objects.filter(pk__in=[self.server.pk, self.other.pk]).delete()
    self.assertEqual(self.jobs_for(repo), 1)

  @override_settings(JOBSERVER_DELETE_AFTER_DAYS=7, JOBSERVER_FAIL_JOBS_AFTER_MINUTES=0)
  def test_auto_delete_queues_only_hostless_mirrored_repos(self):
    mirror = self.repo("mirror", hosts=[self.server])
    upstream = self.repo("upstream", managed=False, hosts=[self.server])
    JobServer.objects.filter(pk=self.server.pk).update(heartbeat_time=timezone.now() - datetime.timedelta(days=8))
    sweep_stale_jobservers()
    self.assertFalse(JobServer.objects.filter(pk=self.server.pk).exists())
    self.assertEqual(self.jobs_for(mirror), 1)
    self.assertEqual(self.jobs_for(upstream), 0)
