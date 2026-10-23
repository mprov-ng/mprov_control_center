import json

from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework_api_key.models import APIKey

from jobqueue.models import Job, JobModule, JobServer, JobStatus


class ScopedAPIKeyTests(TestCase):
  """ A valid API key is a scoped agent credential (#315): it may read model
  endpoints and make exactly the writes the jobserver agent protocol needs
  (register, PATCH job status).  Every other method requires a user login. """

  def setUp(self):
    # init_mpcc.sh creates the admin user alongside the jobserver API key.
    User.objects.create_superuser("admin", "admin@example.com", "password")
    self.module = JobModule.objects.create(slug="nads", name="NADS")
    JobStatus.objects.create(pk=1, name="PENDING")
    JobStatus.objects.create(pk=2, name="RUNNING")
    self.job = Job.objects.create(name="NADS", module=self.module, status_id=1)
    _, self.key = APIKey.objects.create_key(name="mProv Jobserver Key")

  def key_request(self, method, url, data=None):
    return getattr(self.client, method)(
        url, data, content_type="application/json",
        HTTP_AUTHORIZATION="Api-Key " + self.key)

  # -- the jobserver agent protocol keeps working --------------------------
  def test_key_can_read(self):
    self.assertEqual(self.key_request("get", "/jobmodules/").status_code, 200)

  def test_key_can_register_a_jobserver(self):
    response = self.key_request("post", "/jobservers/", json.dumps(
        {"name": "js1", "address": "10.0.0.1", "one_minute_load": 0.5,
         "jobmodules": ["nads"]}))
    self.assertEqual(response.status_code, 200)

  def test_key_can_patch_job_status(self):
    response = self.key_request("patch", "/jobs/%d/" % self.job.pk,
                                json.dumps({"status": 2}))
    self.assertEqual(response.status_code, 200)
    self.job.refresh_from_db()
    self.assertEqual(self.job.status_id, 2)

  # -- unrestricted key writes are the #315 defect --------------------------
  def test_key_cannot_create_jobs(self):
    response = self.key_request("post", "/jobs/",
                                json.dumps({"name": "sneaky", "module": "nads"}))
    self.assertIn(response.status_code, (401, 403), response.content)
    self.assertEqual(Job.objects.count(), 1)

  def test_key_cannot_delete_jobs(self):
    response = self.key_request("delete", "/jobs/%d/" % self.job.pk)
    self.assertIn(response.status_code, (401, 403), response.content)
    self.assertTrue(Job.objects.filter(pk=self.job.pk).exists())

  def test_key_can_register_jobservers_but_not_delete_them(self):
    server = JobServer.objects.create(name="js1", address="10.0.0.1")
    response = self.key_request("delete", "/jobservers/%d/" % server.pk)
    self.assertIn(response.status_code, (401, 403), response.content)
    self.assertTrue(JobServer.objects.filter(pk=server.pk).exists())
