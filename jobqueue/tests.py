import datetime
import json
from unittest import mock

from django.contrib.auth.models import User
from django.utils import timezone
from rest_framework.request import Request
from rest_framework.response import Response

from common.testing import APITestCase
from jobqueue.models import Job, JobModule, JobServer, JobStatus
from jobqueue.views import JobAPIView


class JobQueueURLTests(APITestCase):
  """ /jobqueue/<pk>/ takes a job module slug, and doesn't hide status-changes/. """

  def test_job_module_detail_by_slug(self):
    JobModule.objects.create(slug="pxe-update", name="PXE Update")
    response = self.get_json("/jobqueue/pxe-update/")
    self.assertEqual(response.status_code, 200)
    self.assertEqual(response.json()["slug"], "pxe-update")

  def test_status_changes_still_routed(self):
    response = self.get_json("/jobqueue/status-changes/")
    self.assertEqual(response.status_code, 200)
    self.assertEqual(response.json(), {"changes": []})

  def test_status_changes_need_a_staff_login(self):
    self.client.logout()
    self.assertEqual(self.get_json("/jobqueue/status-changes/").status_code, 403)
    User.objects.create_user("user", password="password")
    self.client.login(username="user", password="password")
    self.assertEqual(self.get_json("/jobqueue/status-changes/").status_code, 403)


class JobDetailTests(APITestCase):
  """ GET /jobs/<pk>/ returns the job. """

  def test_job_detail(self):
    module = JobModule.objects.create(slug="pxe-update", name="PXE Update")
    status = JobStatus.objects.create(name="Pending")
    job = Job.objects.create(name="PXE Update", module=module, status=status)
    response = self.get_json(f"/jobs/{job.pk}/")
    self.assertEqual(response.status_code, 200)
    self.assertEqual(response.json()["id"], job.pk)

  def test_retrieve_gets_the_request(self):
    # retrieve(request, ...), not retrieve(self, request, ...).
    with mock.patch.object(JobAPIView, "retrieve", autospec=True, return_value=Response(None)) as retrieve:
      self.get_json("/jobs/1/")
    view, request = retrieve.call_args.args
    self.assertIsInstance(view, JobAPIView)
    self.assertIsInstance(request, Request)
    self.assertEqual(retrieve.call_args.kwargs, {"pk": 1})


class JobServerRegisterTests(APITestCase):
  """ POST /jobservers/ creates or updates the job server with the given name. """

  def post(self, data):
    return self.client.post("/jobservers/", json.dumps(data), content_type="application/json")

  def test_register(self):
    JobModule.objects.create(slug="nads", name="NADS")
    response = self.post({"name": "js1", "address": "10.0.0.1", "one_minute_load": 0.5, "jobmodules": ["nads"]})
    self.assertEqual(response.status_code, 200)
    server = JobServer.objects.get(name="js1")
    # the jobserver json.loads() the body, so it stays a JSON-encoded string (D-33).
    self.assertEqual(json.loads(response.json()), {"pk": server.pk})
    self.assertEqual(server.port, 8080)
    self.assertEqual(list(server.jobmodules.values_list("slug", flat=True)), ["nads"])

  def test_blank_name_is_400(self):
    response = self.post({"name": "", "address": "10.0.0.1", "one_minute_load": 0.5, "jobmodules": []})
    self.assertEqual(response.status_code, 400)
    self.assertFalse(JobServer.objects.exists())

  def test_missing_fields_are_400(self):
    response = self.post({"name": "js1"})
    self.assertEqual(response.status_code, 400)
    self.assertEqual(set(response.json()), {"address", "one_minute_load", "jobmodules"})

  def test_list_shows_job_modules(self):
    server = JobServer.objects.create(name="js1")
    server.jobmodules.add(JobModule.objects.create(slug="nads", name="NADS"),
                          JobModule.objects.create(slug="dnsmasq", name="DNSMasq"))
    response = self.get_json("/jobservers/")
    self.assertEqual(response.status_code, 200)
    self.assertEqual(sorted(response.json()[0]["jobmodules"]), ["dnsmasq", "nads"])


class StaleJobServerTests(APITestCase):
  """ Saving a job server deletes the others whose heartbeat is over a minute old. """

  def test_stale_servers_are_deleted(self):
    old = timezone.now() - datetime.timedelta(minutes=5)
    JobServer.objects.create(name="fresh")
    stale = JobServer.objects.create(name="stale")
    JobServer.objects.filter(pk=stale.pk).update(heartbeat_time=old)
    me = JobServer.objects.create(name="me")
    JobServer.objects.filter(pk=me.pk).update(heartbeat_time=old)

    me = JobServer.objects.get(pk=me.pk)
    me.heartbeat_time = timezone.now()
    me.save()
    self.assertEqual(sorted(JobServer.objects.values_list("name", flat=True)), ["fresh", "me"])


class JobCreateTests(APITestCase):
  """ POST /jobs/ defaults the status and doesn't need a job server. """

  def test_create_job(self):
    module = JobModule.objects.create(slug="pxe-update", name="PXE Update")
    JobStatus.objects.create(pk=1, name="PENDING")
    response = self.client.post("/jobs/", json.dumps({"name": "PXE Update", "module": module.pk}), content_type="application/json")
    self.assertEqual(response.status_code, 201, response.content)
    job = Job.objects.get()
    self.assertEqual((job.status_id, job.jobserver), (1, None))

  def test_clear_job_server_network(self):
    from networks.models import Network, NetworkType
    net = Network.objects.create(name="lan", net_type=NetworkType.objects.create(name="Ethernet"), netmask=24)
    server = JobServer.objects.create(name="js1", network=net)
    server.jobmodules.add(JobModule.objects.create(slug="nads", name="NADS"))
    response = self.client.patch(f"/jobservers/{server.pk}/", json.dumps({"network": None}), content_type="application/json")
    self.assertEqual(response.status_code, 200, response.content)
    server.refresh_from_db()
    self.assertIsNone(server.network)


class JobParamsFilterTests(APITestCase):
  """ GET /jobs/?params={...} matches jobs by their params' keys. """

  def setUp(self):
    super().setUp()
    module = JobModule.objects.create(slug="repo-update", name="Update Repos")
    status = JobStatus.objects.create(pk=1, name="PENDING")
    for repo_id in (1, 2):
      Job.objects.create(name="Update Repos", module=module, status=status, params={"repo_id": repo_id, "x": "y"})

  def test_filter_by_params(self):
    response = self.client.get("/jobs/", {"params": '{"repo_id": 2}'}, CONTENT_TYPE="application/json")
    self.assertEqual(response.status_code, 200)
    self.assertEqual([job["params"]["repo_id"] for job in response.json()], [2])

  def test_bad_params_is_400(self):
    for value in ("nope", "[1]"):
      response = self.client.get("/jobs/", {"params": value}, CONTENT_TYPE="application/json")
      self.assertEqual(response.status_code, 400, value)


class JobModuleCreateTests(APITestCase):
  """ POST /jobmodules/ sets the module ID; PATCH can't change it. """

  def test_create_with_slug(self):
    response = self.client.post("/jobmodules/", json.dumps({"slug": "ldap-sync", "name": "LDAP Sync"}), content_type="application/json")
    self.assertEqual(response.status_code, 201, response.content)
    self.assertEqual(JobModule.objects.get(pk="ldap-sync").name, "LDAP Sync")

  def test_duplicate_slug_is_400(self):
    JobModule.objects.create(slug="nads", name="NADS")
    response = self.client.post("/jobmodules/", json.dumps({"slug": "nads", "name": "Other"}), content_type="application/json")
    self.assertEqual(response.status_code, 400)

  def test_patch_cannot_change_slug(self):
    JobModule.objects.create(slug="nads", name="NADS")
    response = self.client.patch("/jobmodules/nads/", json.dumps({"slug": "other"}), content_type="application/json")
    self.assertEqual(response.status_code, 400)
    response = self.client.patch("/jobmodules/nads/", json.dumps({"name": "Node Detection"}), content_type="application/json")
    self.assertEqual(response.status_code, 200, response.content)
    self.assertEqual(list(JobModule.objects.values_list("slug", "name")), [("nads", "Node Detection")])
