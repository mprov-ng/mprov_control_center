import importlib
import json
from datetime import timedelta
from unittest import mock

from django.apps import apps
from django.test import override_settings
from django.utils import timezone

from common.testing import APITestCase
from jobqueue.models import Job, JobModule, JobServer, JobStatus, requeue_job, sweep_stale_jobservers
from networks.models import Network, NetworkType
from osmanagement.models import OSRepo
from systems.models import System

PENDING, RUNNING, ERROR, COMPLETE = 1, 2, 3, 4


class JobsTestCase(APITestCase):

  def setUp(self):
    super().setUp()
    for pk, name in ((PENDING, "PENDING"), (RUNNING, "RUNNING"), (ERROR, "ERROR"), (COMPLETE, "COMPLETE")):
      JobStatus.objects.create(pk=pk, name=name)
    self.js1 = JobServer.objects.create(name="js1")
    self.js2 = JobServer.objects.create(name="js2")

  def module(self, slug, name):
    return JobModule.objects.get_or_create(slug=slug, defaults={"name": name})[0]

  def statuses(self, module, name=None):
    return sorted(Job.objects.filter(module=module, name=name or module.name).values_list("status_id", flat=True))


class RequeueJobTests(JobsTestCase):
  """ requeue_job() never resets a running job, so a change made while it runs doesn't make it run twice (#312). """

  def setUp(self):
    super().setUp()
    self.dns = self.module("dns-update", "DNS Update")

  def test_creates_the_job(self):
    job = requeue_job(self.dns)
    self.assertEqual((job.name, job.status_id, job.jobserver_id), ("DNS Update", PENDING, None))

  def test_a_pending_job_is_left_alone(self):
    first = requeue_job(self.dns)
    self.assertEqual(requeue_job(self.dns).pk, first.pk)
    self.assertEqual(self.statuses(self.dns), [PENDING])

  def test_a_running_job_is_left_running_and_a_new_one_queued(self):
    running = Job.objects.create(name="DNS Update", module=self.dns, status_id=RUNNING, jobserver=self.js1)
    queued = requeue_job(self.dns)
    self.assertNotEqual(queued.pk, running.pk)
    running.refresh_from_db()
    self.assertEqual((running.status_id, running.jobserver_id), (RUNNING, self.js1.pk))
    self.assertEqual(self.statuses(self.dns), [PENDING, RUNNING])
    # a second change while it still runs doesn't queue a third.
    self.assertEqual(requeue_job(self.dns).pk, queued.pk)
    self.assertEqual(self.statuses(self.dns), [PENDING, RUNNING])

  def test_a_finished_job_is_reused(self):
    for status in (COMPLETE, ERROR):
      Job.objects.all().delete()
      done = Job.objects.create(name="DNS Update", module=self.dns, status_id=status, jobserver=self.js1)
      job = requeue_job(self.dns)
      self.assertEqual(job.pk, done.pk)
      job.refresh_from_db()
      self.assertEqual((job.status_id, job.jobserver_id), (PENDING, None))
      self.assertEqual(self.statuses(self.dns), [PENDING])

  def test_works_again_after_a_running_and_a_pending_row(self):
    # the old update_or_create() raised MultipleObjectsReturned with two rows.
    Job.objects.create(name="DNS Update", module=self.dns, status_id=RUNNING, jobserver=self.js1)
    requeue_job(self.dns)
    requeue_job(self.dns)
    self.assertEqual(self.statuses(self.dns), [PENDING, RUNNING])

  def test_name_other_than_the_module_name(self):
    delete = self.module("repo-delete", "Delete Repo")
    job = requeue_job(delete, "Delete Repos")
    self.assertEqual(job.name, "Delete Repos")
    self.assertEqual(self.statuses(delete, "Delete Repos"), [PENDING])

  def test_other_modules_are_left_alone(self):
    pxe = self.module("pxe-update", "PXE Update")
    running = Job.objects.create(name="PXE Update", module=pxe, status_id=RUNNING, jobserver=self.js1)
    requeue_job(self.dns)
    running.refresh_from_db()
    self.assertEqual(running.status_id, RUNNING)
    self.assertEqual(self.statuses(pxe), [RUNNING])


class ChangeSignalTests(JobsTestCase):
  """ The change signals queue their jobs through requeue_job() (#312). """

  def setUp(self):
    super().setUp()
    self.modules = {slug: self.module(slug, name) for slug, name in (
      ("pxe-update", "PXE Update"), ("dns-update", "DNS Update"), ("dhcp-update", "DHCP Update"),
      ("pxe-delete", "PXE Delete"), ("dns-delete", "DNS Delete"), ("dhcp-delete", "DHCP Delete"),
      ("libgenders", "Genders"), ("repo-delete", "Delete Repo"))}
    self.running = {slug: Job.objects.create(name=module.name if slug != "repo-delete" else "Delete Repos",
                                             module=module, status_id=RUNNING, jobserver=self.js1)
                    for slug, module in self.modules.items()}

  def assertRequeued(self, *slugs):
    for slug in slugs:
      job = self.running[slug]
      job.refresh_from_db()
      self.assertEqual((job.status_id, job.jobserver_id), (RUNNING, self.js1.pk), slug)
      self.assertEqual(self.statuses(self.modules[slug], job.name), [PENDING, RUNNING], slug)

  def test_network_save_and_delete(self):
    network = Network.objects.create(name="LAN", net_type=NetworkType.objects.create(name="Ethernet"),
                                     subnet="172.16.0.0", netmask=16)
    self.assertRequeued("pxe-update", "dns-update", "dhcp-update")
    network.delete()
    self.assertRequeued("pxe-delete", "dns-delete", "dhcp-delete")

  def test_system_save(self):
    System.objects.create(hostname="node01", created_by=self.user)
    self.assertRequeued("pxe-update", "dns-update", "dhcp-update", "libgenders")

  def test_repo_delete(self):
    OSRepo.objects.create(name="BaseOS", repo_package_url="http://mirror/").delete()
    self.assertRequeued("repo-delete")


class RunningJobsTestCase(JobsTestCase):
  """ A running job on each job server, plus a finished and a pending one. """

  def setUp(self):
    super().setUp()
    self.dns = self.module("dns-update", "DNS Update")
    self.mine = Job.objects.create(name="mine", module=self.dns, status_id=RUNNING, jobserver=self.js1)
    self.mine_done = Job.objects.create(name="done", module=self.dns, status_id=COMPLETE, jobserver=self.js1)
    self.pending = Job.objects.create(name="pending", module=self.dns)
    self.theirs = Job.objects.create(name="theirs", module=self.dns, status_id=RUNNING, jobserver=self.js2)

  def assertOnlyMineFailed(self):
    for job in (self.mine, self.mine_done, self.pending, self.theirs):
      job.refresh_from_db()
    self.assertEqual((self.mine.status_id, self.mine.jobserver_id), (ERROR, None))
    self.assertIsNotNone(self.mine.end_time)
    self.assertEqual(self.mine_done.status_id, COMPLETE)
    self.assertEqual(self.pending.status_id, PENDING)
    self.assertEqual((self.theirs.status_id, self.theirs.jobserver_id), (RUNNING, self.js2.pk))


class DeletedJobServerTests(RunningJobsTestCase):
  """ Deleting a job server fails the jobs it was running; nothing else would ever finish them (#409). """

  def test_delete_fails_its_running_jobs(self):
    self.js1.delete()
    self.assertOnlyMineFailed()

  def test_admin_delete(self):
    response = self.client.post(f"/admin/jobqueue/jobserver/{self.js1.pk}/delete/", {"post": "yes"})
    self.assertEqual(response.status_code, 302)
    self.assertOnlyMineFailed()

  def test_saving_never_deletes_a_stale_server(self):
    """ #254: the stale delete in JobServer.save() is gone. """
    JobServer.objects.filter(pk=self.js1.pk).update(heartbeat_time="2020-01-01T00:00:00Z")
    self.js2.save()
    self.assertTrue(JobServer.objects.filter(pk=self.js1.pk).exists())
    self.mine.refresh_from_db()
    self.assertEqual((self.mine.status_id, self.mine.jobserver_id), (RUNNING, self.js1.pk))

  def test_migration_fails_existing_orphans(self):
    orphan = Job.objects.create(name="orphan", module=self.dns, status_id=RUNNING)
    migration = importlib.import_module("jobqueue.migrations.0018_fail_orphaned_running_jobs")
    migration.fail_orphaned_running_jobs(apps, None)
    orphan.refresh_from_db()
    self.assertEqual(orphan.status_id, ERROR)
    self.assertIsNotNone(orphan.end_time)
    self.mine.refresh_from_db()
    self.assertEqual(self.mine.status_id, RUNNING)


class StaleJobServerSweepTests(RunningJobsTestCase):
  """ Unresponsive job servers are kept; their jobs are failed after a grace
  period, and they're deleted only if JOBSERVER_DELETE_AFTER_DAYS is set (#254). """

  def unresponsive_for(self, server, age):
    JobServer.objects.filter(pk=server.pk).update(heartbeat_time=timezone.now() - age)

  def assertNothingFailed(self):
    for job in (self.mine, self.theirs):
      job.refresh_from_db()
      self.assertEqual(job.status_id, RUNNING)

  def test_running_jobs_fail_after_the_grace_period(self):
    self.unresponsive_for(self.js1, timedelta(minutes=11))
    sweep_stale_jobservers()
    self.assertTrue(JobServer.objects.filter(pk=self.js1.pk).exists())
    for job in (self.mine, self.mine_done, self.pending, self.theirs):
      job.refresh_from_db()
    self.assertEqual((self.mine.status_id, self.mine.jobserver_id), (ERROR, self.js1.pk))
    self.assertIsNotNone(self.mine.end_time)
    self.assertEqual((self.mine_done.status_id, self.pending.status_id), (COMPLETE, PENDING))
    self.assertEqual(self.theirs.status_id, RUNNING)

  def test_running_jobs_are_kept_within_the_grace_period(self):
    self.unresponsive_for(self.js1, timedelta(minutes=5))
    sweep_stale_jobservers()
    self.assertNothingFailed()

  @override_settings(JOBSERVER_FAIL_JOBS_AFTER_MINUTES=0)
  def test_zero_turns_job_failing_off(self):
    self.unresponsive_for(self.js1, timedelta(days=30))
    sweep_stale_jobservers()
    self.assertNothingFailed()

  def test_no_delete_by_default(self):
    self.unresponsive_for(self.js1, timedelta(days=365))
    sweep_stale_jobservers()
    self.assertTrue(JobServer.objects.filter(pk=self.js1.pk).exists())

  @override_settings(JOBSERVER_DELETE_AFTER_DAYS=7, JOBSERVER_FAIL_JOBS_AFTER_MINUTES=0)
  def test_delete_after_the_configured_days(self):
    self.unresponsive_for(self.js1, timedelta(days=8))
    self.unresponsive_for(self.js2, timedelta(days=6))
    sweep_stale_jobservers()
    self.assertFalse(JobServer.objects.filter(pk=self.js1.pk).exists())
    self.assertTrue(JobServer.objects.filter(pk=self.js2.pk).exists())
    # through the delete signals: its jobs are failed even with job failing off.
    self.assertOnlyMineFailed()

  def test_registration_sweeps_at_most_once_a_minute(self):
    body = json.dumps({"name": "js3", "address": "10.0.0.3", "one_minute_load": 0.1, "jobmodules": []})
    with mock.patch("jobqueue.views.sweep_stale_jobservers") as sweep:
      for _ in range(3):
        self.assertEqual(self.client.post("/jobservers/", body, content_type="application/json").status_code, 200)
    sweep.assert_called_once_with()

  def test_registration_sweep_fails_the_jobs(self):
    self.unresponsive_for(self.js1, timedelta(minutes=11))
    body = json.dumps({"name": "js2", "address": "10.0.0.2", "one_minute_load": 0.1, "jobmodules": []})
    self.client.post("/jobservers/", body, content_type="application/json")
    self.mine.refresh_from_db()
    self.assertEqual(self.mine.status_id, ERROR)
