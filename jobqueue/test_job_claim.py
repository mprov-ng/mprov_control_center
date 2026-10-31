import importlib
import json

from django.apps import apps
from django.core.cache import cache
from django.test import Client

from common.testing import APITestCase
from jobqueue.models import Job, JobModule, JobServer, JobStatus

PENDING, RUNNING, ERROR, COMPLETE = 1, 2, 3, 4


class JobClaimTests(APITestCase):
  """ POST /jobs/<id>/claim/ claims a pending job for one job server, atomically (#296). """

  def setUp(self):
    super().setUp()
    for pk, name in ((PENDING, "PENDING"), (RUNNING, "RUNNING"), (ERROR, "ERROR"), (COMPLETE, "COMPLETE")):
      JobStatus.objects.create(pk=pk, name=name)
    self.module = JobModule.objects.create(slug="dns-update", name="DNS Update")
    self.js1 = JobServer.objects.create(name="js1")
    self.js2 = JobServer.objects.create(name="js2")
    self.job = Job.objects.create(name="DNS Update", module=self.module)

  def claim(self, data, job=None, client=None):
    job = self.job if job is None else job
    return (client or self.client).post(f"/jobs/{job.pk}/claim/", json.dumps(data), content_type="application/json")

  def test_claim_a_pending_job(self):
    response = self.claim({"jobserver": self.js1.pk})
    self.assertEqual(response.status_code, 200, response.content)
    self.assertEqual((response.json()["id"], response.json()["status"], response.json()["jobserver"]), (self.job.pk, RUNNING, self.js1.pk))
    self.job.refresh_from_db()
    self.assertEqual((self.job.status_id, self.job.jobserver_id), (RUNNING, self.js1.pk))
    self.assertIsNotNone(self.job.start_time)
    self.assertIsNone(self.job.end_time)

  def test_second_claim_gets_409(self):
    self.assertEqual(self.claim({"jobserver": self.js1.pk}).status_code, 200)
    response = self.claim({"jobserver": self.js2.pk})
    self.assertEqual(response.status_code, 409, response.content)
    self.assertEqual((response.json()["status"], response.json()["jobserver"]), (RUNNING, self.js1.pk))
    self.job.refresh_from_db()
    self.assertEqual(self.job.jobserver_id, self.js1.pk)

  def test_same_server_claiming_its_running_job_again_gets_409(self):
    self.claim({"jobserver": self.js1.pk})
    self.assertEqual(self.claim({"jobserver": self.js1.pk}).status_code, 409)

  def test_jobs_that_arent_pending_get_409(self):
    for status in (RUNNING, ERROR, COMPLETE):
      job = Job.objects.create(name="DNS Update", module=self.module, status_id=status)
      response = self.claim({"jobserver": self.js1.pk}, job=job)
      self.assertEqual(response.status_code, 409, status)
      job.refresh_from_db()
      self.assertEqual((job.status_id, job.jobserver_id), (status, None))

  def test_job_id_as_a_string_works(self):
    # the jobserver's config could hand it over as text.
    self.assertEqual(self.claim({"jobserver": str(self.js1.pk)}).status_code, 200)

  def test_bad_jobserver_is_400(self):
    for data in ({}, {"jobserver": None}, {"jobserver": "js1"}, {"jobserver": True}, {"jobserver": [1]}, {"jobserver": 999}):
      response = self.claim(data)
      self.assertEqual(response.status_code, 400, data)
      self.assertIn("jobserver", response.json())
    self.job.refresh_from_db()
    self.assertEqual((self.job.status_id, self.job.jobserver_id), (PENDING, None))

  def test_unknown_job_is_404(self):
    response = self.client.post("/jobs/999/claim/", json.dumps({"jobserver": self.js1.pk}), content_type="application/json")
    self.assertEqual(response.status_code, 404)

  def test_needs_authentication(self):
    response = self.claim({"jobserver": self.js1.pk}, client=Client())
    self.assertIn(response.status_code, (401, 403))
    self.job.refresh_from_db()
    self.assertEqual(self.job.status_id, PENDING)

  def test_get_is_not_allowed(self):
    response = self.client.get(f"/jobs/{self.job.pk}/claim/", CONTENT_TYPE="application/json")
    self.assertEqual(response.status_code, 405)

  def test_claim_shows_a_status_change_toast(self):
    cache.clear()
    self.claim({"jobserver": self.js1.pk})
    changes = [cache.get(key) for key in cache.get("recent_job_status_changes", [])]
    self.assertIn((self.job.pk, "PENDING", "RUNNING"), [(c["job_id"], c["old_status"], c["new_status"]) for c in changes])

  def test_job_claim_is_a_listed_feature(self):
    from jobqueue.views import FEATURES
    self.assertIn("job-claim", FEATURES)


class PendingJobsHaveNoJobServerTests(APITestCase):
  """ A pending job belongs to no job server: setting a job back to pending clears it (#296). """

  def setUp(self):
    super().setUp()
    for pk, name in ((PENDING, "PENDING"), (RUNNING, "RUNNING"), (ERROR, "ERROR"), (COMPLETE, "COMPLETE")):
      JobStatus.objects.create(pk=pk, name=name)
    self.module = JobModule.objects.create(slug="dns-update", name="DNS Update")
    self.js1 = JobServer.objects.create(name="js1")

  def test_create_pending_with_a_jobserver_drops_it(self):
    job = Job.objects.create(name="DNS Update", module=self.module, jobserver=self.js1)
    self.assertIsNone(job.jobserver_id)

  def test_a_change_signal_reset_clears_the_jobserver(self):
    # the update_or_create(defaults={'status': PENDING}) re-queueing in the
    # change signals (#312) used to leave the running job server on the job.
    job = Job.objects.create(name="DNS Update", module=self.module, status_id=RUNNING, jobserver=self.js1)
    Job.objects.update_or_create(name="DNS Update", module=self.module, defaults={'status': JobStatus.objects.get(pk=PENDING)})
    job.refresh_from_db()
    self.assertEqual((job.status_id, job.jobserver_id), (PENDING, None))

  def test_patch_to_pending_clears_the_jobserver(self):
    job = Job.objects.create(name="DNS Update", module=self.module, status_id=RUNNING, jobserver=self.js1)
    response = self.client.patch(f"/jobs/{job.pk}/", json.dumps({"status": PENDING}), content_type="application/json")
    self.assertEqual(response.status_code, 200, response.content)
    self.assertIsNone(response.json()["jobserver"])

  def test_running_and_finished_jobs_keep_their_jobserver(self):
    for status in (RUNNING, ERROR, COMPLETE):
      job = Job.objects.create(name="DNS Update", module=self.module, status_id=status, jobserver=self.js1)
      job.refresh_from_db()
      self.assertEqual(job.jobserver_id, self.js1.pk)

  def test_migration_clears_existing_pending_jobs(self):
    pending = Job.objects.create(name="DNS Update", module=self.module)
    running = Job.objects.create(name="DNS Update", module=self.module, status_id=RUNNING, jobserver=self.js1)
    # put a pending job in the state the old signals left it in.
    Job.objects.filter(pk=pending.pk).update(jobserver=self.js1)
    migration = importlib.import_module("jobqueue.migrations.0017_pending_jobs_have_no_jobserver")
    migration.clear_pending_jobservers(apps, None)
    pending.refresh_from_db()
    running.refresh_from_db()
    self.assertIsNone(pending.jobserver_id)
    self.assertEqual(running.jobserver_id, self.js1.pk)
