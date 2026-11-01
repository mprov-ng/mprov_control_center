import json

from common.testing import APITestCase
from jobqueue.models import JobModule, JobServer


class JobServerRegisterTests(APITestCase):
  """ POST /jobservers/ creates or updates the job server with the given name. """

  def post(self, data):
    return self.client.post("/jobservers/", json.dumps(data), content_type="application/json")

  def test_register(self):
    JobModule.objects.create(slug="nads", name="NADS")
    response = self.post({"name": "js1", "address": "10.0.0.1", "one_minute_load": 0.5, "jobmodules": ["nads"]})
    self.assertEqual(response.status_code, 200)
    server = JobServer.objects.get(name="js1")
    # a plain object, not a JSON-encoded string (D-33, #268, #447).
    self.assertEqual(response.json(), {"pk": server.pk, "features": ["addjs-version", "host-id", "jobserver-addresses", "job-claim", "jobserver-address-heartbeat"]})
    self.assertEqual(server.port, 8080)
    self.assertEqual(list(server.jobmodules.values_list("slug", flat=True)), ["nads"])

  def test_reply_is_an_object_with_or_without_host_id(self):
    """ Issues #406, #268, #447: the reply lists the optional API features, as
    a plain object, whether or not the job server sends host_id.  The
    JSON-encoded string v0.0.62 needed is gone: v0.0.62 sends no
    mProv-Version, so the version lock answers it 426 first (#452). """
    from jobqueue.views import FEATURES
    for name, extra in (("js1", {}), ("js2", {"host_id": "abc"})):
      with self.subTest(host_id=extra.get("host_id")):
        response = self.post({"name": name, "address": "10.0.0.1", "one_minute_load": 0.5, "jobmodules": [], **extra})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"pk": JobServer.objects.get(name=name).pk, "features": FEATURES})
        self.assertIn("addjs-version", response.json()["features"])

  def test_unknown_module_is_created(self):
    # a job server creates the modules it runs (#256); it used to be a 500.
    response = self.post({"name": "js1", "address": "10.0.0.1", "one_minute_load": 0.5, "jobmodules": ["new-module"]})
    self.assertEqual(response.status_code, 200)
    self.assertEqual(list(JobServer.objects.get(name="js1").jobmodules.values_list("slug", "name")), [("new-module", "new-module")])

  def test_blank_name_is_400(self):
    response = self.post({"name": "", "address": "10.0.0.1", "one_minute_load": 0.5, "jobmodules": []})
    self.assertEqual(response.status_code, 400)
    self.assertFalse(JobServer.objects.exists())

  def test_missing_fields_are_400(self):
    response = self.post({"name": "js1"})
    self.assertEqual(response.status_code, 400)
    self.assertEqual(set(response.json()), {"address", "one_minute_load", "jobmodules"})

  def test_bad_types_are_400(self):
    # issue #328: these failed inside update_or_create() or the jobmodules loop with a 500.
    response = self.post({"name": "js1", "address": "10.0.0.1", "one_minute_load": "high", "port": "http",
                          "jobmodules": "nads"})
    self.assertEqual(response.status_code, 400)
    self.assertEqual(set(response.json()), {"one_minute_load", "port", "jobmodules"})
    self.assertFalse(JobServer.objects.exists())

  def test_port_from_yaml_as_a_string(self):
    # the jobserver sends its config's serverPort, which a site may have quoted.
    response = self.post({"name": "js1", "address": "10.0.0.1", "one_minute_load": 0.5, "port": "8081",
                          "jobmodules": []})
    self.assertEqual(response.status_code, 200)
    self.assertEqual(JobServer.objects.get(name="js1").port, 8081)
