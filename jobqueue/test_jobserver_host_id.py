import json

from common.testing import APITestCase
from jobqueue.models import JobModule, JobServer


class JobServerHostIdTests(APITestCase):
  """ mprov_jobserver#113: POST /jobservers/ with a host_id finds the job
  server by it, so a renamed job server keeps its row. """

  def setUp(self):
    super().setUp()
    JobModule.objects.create(slug="nads", name="NADS")

  def post(self, **data):
    body = {"name": "js1", "address": "10.0.0.1", "one_minute_load": 0.5, "jobmodules": ["nads"], **data}
    return self.client.post("/jobservers/", json.dumps(body), content_type="application/json")

  def registered(self, response):
    self.assertEqual(response.status_code, 200, response.content)
    return JobServer.objects.get(pk=json.loads(response.json())["pk"])

  def test_new_job_server_gets_its_host_id(self):
    server = self.registered(self.post(host_id="abc"))
    self.assertEqual((server.name, server.host_id), ("js1", "abc"))
    self.assertEqual(list(server.jobmodules.values_list("slug", flat=True)), ["nads"])

  def test_rename_keeps_the_same_row(self):
    first = self.registered(self.post(host_id="abc"))
    renamed = self.registered(self.post(host_id="abc", name="js2", address="10.0.0.2", port=8081, one_minute_load=1.5))
    self.assertEqual(renamed.pk, first.pk)
    self.assertEqual((renamed.name, renamed.address, renamed.port, renamed.one_minute_load), ("js2", "10.0.0.2", 8081, 1.5))
    self.assertEqual(JobServer.objects.count(), 1)

  def test_row_without_a_host_id_is_adopted(self):
    # the first heartbeat after the job server is upgraded.
    old = JobServer.objects.create(name="js1", address="10.0.0.1")
    server = self.registered(self.post(host_id="abc"))
    self.assertEqual(server.pk, old.pk)
    self.assertEqual(server.host_id, "abc")
    self.assertEqual(JobServer.objects.count(), 1)

  def test_name_of_another_job_server_is_409(self):
    other = JobServer.objects.create(name="js1", address="10.0.0.9", host_id="xyz")
    response = self.post(host_id="abc")
    self.assertEqual(response.status_code, 409)
    self.assertEqual(response.json(), {"detail": "name js1 is registered by another job server"})
    other.refresh_from_db()
    self.assertEqual((other.address, other.host_id), ("10.0.0.9", "xyz"))
    self.assertEqual(JobServer.objects.count(), 1)

  def test_renaming_onto_another_job_servers_name_is_409(self):
    mine = self.registered(self.post(host_id="abc"))
    for other_host_id in ("xyz", None):
      with self.subTest(other_host_id=other_host_id):
        JobServer.objects.filter(name="js2").delete()
        JobServer.objects.create(name="js2", address="10.0.0.9", host_id=other_host_id)
        response = self.post(host_id="abc", name="js2")
        self.assertEqual(response.status_code, 409)
        mine.refresh_from_db()
        self.assertEqual(mine.name, "js1")

  def test_without_a_host_id_the_name_is_used_as_before(self):
    server = self.registered(self.post(host_id="abc"))
    # an older job server, or the same one rolled back, still matches by name.
    again = self.registered(self.post(address="10.0.0.3"))
    self.assertEqual(again.pk, server.pk)
    self.assertEqual((again.address, again.host_id), ("10.0.0.3", "abc"))
    legacy = self.registered(self.post(name="js9"))
    self.assertIsNone(legacy.host_id)

  def test_surrounding_whitespace_is_dropped(self):
    first = self.registered(self.post(host_id=" abc\n"))
    self.assertEqual(first.host_id, "abc")
    self.assertEqual(self.registered(self.post(host_id="abc")).pk, first.pk)

  def test_bad_host_id_is_400(self):
    for host_id in ("", "   ", 123, None, ["abc"], "x" * 65):
      with self.subTest(host_id=host_id):
        response = self.post(host_id=host_id)
        self.assertEqual(response.status_code, 400)
        self.assertIn("host_id", response.json())
    self.assertFalse(JobServer.objects.exists())

  def test_host_id_is_read_only_through_patch(self):
    server = self.registered(self.post(host_id="abc"))
    response = self.client.patch(f"/jobservers/{server.pk}/", json.dumps({"host_id": "evil", "address": "10.0.0.7"}),
                                 content_type="application/json")
    self.assertEqual(response.status_code, 200, response.content)
    server.refresh_from_db()
    self.assertEqual((server.host_id, server.address), ("abc", "10.0.0.7"))

  def test_reply_lists_the_host_id_feature(self):
    response = self.post(host_id="abc")
    self.assertIsInstance(response.json(), str)
    self.assertIn("host-id", json.loads(response.json())["features"])

  def test_admin_shows_host_id_read_only(self):
    server = self.registered(self.post(host_id="abc-123"))
    changelist = self.client.get("/admin/jobqueue/jobserver/")
    self.assertContains(changelist, "abc-123")
    change = self.client.get(f"/admin/jobqueue/jobserver/{server.pk}/change/")
    self.assertContains(change, "abc-123")
    self.assertNotContains(change, 'name="host_id"')
