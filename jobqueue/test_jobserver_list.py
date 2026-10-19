import json

from common.testing import APITestCase
from jobqueue.models import JobModule, JobServer


class JobServerRegisterTests(APITestCase):
  """ POST /jobservers/ creates or updates the job server with the given name. """

  def post(self, data):
    return self.client.post("/jobservers/", json.dumps(data), content_type="application/json")

  def test_list_shows_job_modules(self):
    server = JobServer.objects.create(name="js1")
    server.jobmodules.add(JobModule.objects.create(slug="nads", name="NADS"),
                          JobModule.objects.create(slug="dnsmasq", name="DNSMasq"))
    response = self.get_json("/jobservers/")
    self.assertEqual(response.status_code, 200)
    self.assertEqual(sorted(response.json()[0]["jobmodules"]), ["dnsmasq", "nads"])
