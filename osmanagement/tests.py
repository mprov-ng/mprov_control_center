from bs4 import BeautifulSoup
from django.test import TestCase

from jobqueue.models import Job, JobModule, JobServer, JobStatus
from osmanagement.admin import mark_update
from osmanagement.models import OSDistro, OSRepo


class OSRepoListTests(TestCase):
  """ The unauthenticated /osrepos/ page lists repos as HTML, escaping admin-set values. """

  def test_repo_name_and_url_are_escaped(self):
    OSRepo.objects.create(name="<script>alert(1)</script>", repo_package_url="http://repo/'onmouseover='alert(2)")
    OSRepo.objects.create(name="<b>managed</b>", repo_package_url="http://unused/", managed=True)
    response = self.client.get("/osrepos/")
    self.assertEqual(response.status_code, 200)
    content = response.content.decode()
    self.assertNotIn("<script>alert(1)", content)
    self.assertNotIn("<b>managed</b>", content)
    links = BeautifulSoup(content, features="html.parser").select("ul li a")
    self.assertEqual([a.get_text() for a in links], ["<b>managed</b>", "<script>alert(1)</script>"])
    self.assertEqual(links[1]["href"], "http://repo/'onmouseover='alert(2)")
    self.assertNotIn("onmouseover", links[1].attrs)


class OSDistroCreateReposTests(TestCase):
  """ Saving a distro with update set creates its repos under the base URL. """

  def test_trailing_slash_is_stripped(self):
    OSDistro.objects.create(name="Rocky 9", vendor="Rocky", version="9", update=True,
                            baseurl="http://mirror/rocky/9/")
    self.assertEqual(OSRepo.objects.get(name="BaseOS-9").repo_package_url,
                     "http://mirror/rocky/9/BaseOS/x86_64/os/")


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
