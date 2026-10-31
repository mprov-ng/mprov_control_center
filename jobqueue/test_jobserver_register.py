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
    # the jobserver json.loads() the body, so it stays a JSON-encoded string (D-33).
    self.assertEqual(json.loads(response.json()), {"pk": server.pk, "features": ["addjs-version", "host-id", "jobserver-addresses", "job-claim"]})
    self.assertEqual(server.port, 8080)
    self.assertEqual(list(server.jobmodules.values_list("slug", flat=True)), ["nads"])

  def test_reply_lists_features_and_stays_double_encoded(self):
    """ Issue #406: the reply lists the optional API features, still as a JSON string. """
    from jobqueue.views import FEATURES
    response = self.post({"name": "js1", "address": "10.0.0.1", "one_minute_load": 0.5, "jobmodules": []})
    self.assertEqual(response.status_code, 200)
    # mprov_jobserver v0.0.62 rejects a reply that is already an object (#268).
    self.assertIsInstance(response.json(), str)
    reply = json.loads(response.json())
    self.assertEqual(reply["pk"], JobServer.objects.get(name="js1").pk)
    self.assertEqual(reply["features"], FEATURES)
    self.assertIn("addjs-version", reply["features"])

  def test_unknown_module_is_500(self):
    # the jobserver can't register a module the mPCC doesn't know (#256).
    response = self.post({"name": "js1", "address": "10.0.0.1", "one_minute_load": 0.5, "jobmodules": ["no-such-module"]})
    self.assertEqual(response.status_code, 500)
    self.assertIn("Error locating jobmodule: no-such-module", json.loads(response.json())["msg"])

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
