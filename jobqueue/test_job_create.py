import json

from common.testing import APITestCase
from jobqueue.models import Job, JobModule, JobServer, JobStatus


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
