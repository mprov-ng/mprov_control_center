import json

from common.testing import APITestCase
from jobqueue.models import JobModule, JobServer


class JobModulesFromRegistrationTests(APITestCase):
  """ Job modules are created only by the job servers that run them, when
  they register through POST /jobservers/ (#256). """

  def register(self, *modules):
    body = {"name": "js1", "address": "10.0.0.1", "one_minute_load": 0.5, "jobmodules": list(modules)}
    return self.client.post("/jobservers/", json.dumps(body), content_type="application/json")

  def test_registering_creates_unknown_modules(self):
    JobModule.objects.create(slug="dns-update", name="DNS Update")
    response = self.register("dns-update", "gpu-burn", "slurm_conf")
    self.assertEqual(response.status_code, 200, response.content)
    self.assertEqual(sorted(JobModule.objects.values_list("slug", "name")),
                     [("dns-update", "DNS Update"), ("gpu-burn", "gpu-burn"), ("slurm_conf", "slurm_conf")])
    self.assertEqual(sorted(JobServer.objects.get(name="js1").jobmodules.values_list("slug", flat=True)),
                     ["dns-update", "gpu-burn", "slurm_conf"])

  def test_a_known_module_keeps_its_name(self):
    JobModule.objects.create(slug="nads", name="Node Auto-Detect")
    self.register("nads")
    self.register("nads")
    self.assertEqual(list(JobModule.objects.values_list("slug", "name")), [("nads", "Node Auto-Detect")])

  def test_invalid_module_ids_are_400_and_register_nothing(self):
    for bad in ("", "Has Space", "UPPER", "a/b", 5, None, "x" * 256):
      with self.subTest(bad=bad):
        response = self.register("dns-update", bad)
        self.assertEqual(response.status_code, 400)
        self.assertIn("jobmodules", response.json())
    self.assertFalse(JobServer.objects.exists())
    self.assertFalse(JobModule.objects.exists())

  def test_post_jobmodules_is_405(self):
    response = self.client.post("/jobmodules/", json.dumps({"slug": "x", "name": "X"}), content_type="application/json")
    self.assertEqual(response.status_code, 405)
    self.assertFalse(JobModule.objects.exists())

  def test_patch_renames_but_keeps_the_id(self):
    JobModule.objects.create(slug="gpu-burn", name="gpu-burn")
    response = self.client.patch("/jobmodules/gpu-burn/", json.dumps({"name": "GPU Burn-in", "slug": "other"}),
                                 content_type="application/json")
    self.assertEqual(response.status_code, 200, response.content)
    self.assertEqual(list(JobModule.objects.values_list("slug", "name")), [("gpu-burn", "GPU Burn-in")])

  def test_admin_can_edit_but_not_add(self):
    JobModule.objects.create(slug="gpu-burn", name="gpu-burn")
    self.assertEqual(self.client.get("/admin/jobqueue/jobmodule/add/").status_code, 403)
    self.assertEqual(self.client.get("/admin/jobqueue/jobmodule/gpu-burn/change/").status_code, 200)
    self.assertNotContains(self.client.get("/admin/jobqueue/jobmodule/"), "/admin/jobqueue/jobmodule/add/")
