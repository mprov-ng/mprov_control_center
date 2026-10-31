import json
from datetime import timedelta

from django.utils import timezone

from common.testing import APITestCase
from jobqueue.models import Job, JobModule, JobServer, JobStatus, requeue_job

PENDING, RUNNING, ERROR, COMPLETE = 1, 2, 3, 4


class JobLastUpdateTests(APITestCase):
  """ Job.last_update is the time of the job's last change (#440). """

  def setUp(self):
    super().setUp()
    for pk, name in ((PENDING, "PENDING"), (RUNNING, "RUNNING"), (ERROR, "ERROR"), (COMPLETE, "COMPLETE")):
      JobStatus.objects.create(pk=pk, name=name)
    self.module = JobModule.objects.create(slug="dns-update", name="DNS Update")
    self.server = JobServer.objects.create(name="js1")
    self.long_ago = timezone.now() - timedelta(days=3)

  def job(self, **fields):
    job = Job.objects.create(name="DNS Update", module=self.module, **fields)
    # as an older row would be, from before the change.
    Job.objects.filter(pk=job.pk).update(last_update=self.long_ago)
    return job

  def last_update(self, job):
    return Job.objects.get(pk=job.pk).last_update

  def assertRecent(self, value):
    self.assertLess(abs((timezone.now() - value).total_seconds()), 5)

  def test_create_sets_it(self):
    self.assertRecent(Job.objects.create(name="x", module=self.module).last_update)

  def test_requeue_moves_it(self):
    job = self.job(status_id=COMPLETE)
    self.assertEqual(requeue_job(self.module).pk, job.pk)
    self.assertRecent(self.last_update(job))

  def test_a_status_patch_moves_it(self):
    job = self.job(status_id=RUNNING, jobserver=self.server)
    response = self.client.patch(f"/jobs/{job.pk}/", json.dumps({"status": COMPLETE}), content_type="application/json")
    self.assertEqual(response.status_code, 200, response.content)
    self.assertRecent(self.last_update(job))

  def test_the_claim_sets_it(self):
    job = self.job()
    response = self.client.post(f"/jobs/{job.pk}/claim/", json.dumps({"jobserver": self.server.pk}), content_type="application/json")
    self.assertEqual(response.status_code, 200, response.content)
    self.assertRecent(self.last_update(job))

  def test_a_client_cant_set_it(self):
    job = self.job(status_id=RUNNING, jobserver=self.server)
    self.client.patch(f"/jobs/{job.pk}/", json.dumps({"status": COMPLETE, "last_update": "2001-01-01T00:00:00Z"}),
                      content_type="application/json")
    self.assertRecent(self.last_update(job))
