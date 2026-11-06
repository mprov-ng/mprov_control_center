import json
from datetime import timedelta
from unittest import mock

from django.utils import timezone

from common.testing import APITestCase
from jobqueue.models import JobModule
from systems.models import NetworkInterface, System
from systems.test_provision import ProvisionTestCase

LOGGER = "mprov.provisioning"


class SelfBootedTests(ProvisionTestCase):
  """ #433: POST /systems/?self {"booted": true} from a node logs that it has
  booted and saves its last_booted time; {"netboot": false} from the
  stateful installer logs that it has installed its image.  The lines are in
  the job server's "provisioning: c01 (10.0.0.21) requested image compute"
  shape, for a time-to-provision metric. """

  def setUp(self):
    super().setUp()
    self.client.force_login(self.user)
    self.eth0 = NetworkInterface.objects.create(system=self.system, name="eth0", ipaddress="10.0.0.20", bootable=True)

  def post_self(self, body, ip="10.0.0.20"):
    return self.client.post("/systems/?self", json.dumps(body), content_type="application/json", REMOTE_ADDR=ip)

  def last_booted(self):
    return System.objects.get(pk=self.system.pk).last_booted

  def test_booted_is_logged_and_saved(self):
    before = timezone.now()
    with self.assertLogs(LOGGER, "INFO") as logs:
      response = self.post_self({"booted": True})
    self.assertEqual(response.status_code, 200, response.content)
    self.assertEqual(response.json(), {"provision": True, "bootable_nic": "eth0"})
    self.assertEqual(logs.output, [f"INFO:{LOGGER}:provisioning: prov-node (10.0.0.20) booted image {self.image.slug}"])
    self.assertTrue(before <= self.last_booted() <= timezone.now())
    self.assertTrue(System.objects.get(pk=self.system.pk).provision)

  def test_booted_as_a_string_is_accepted(self):
    self.assertEqual(self.post_self({"booted": "true"}).status_code, 200)
    self.assertIsNotNone(self.last_booted())

  def test_booted_must_be_true(self):
    for value in (False, "false", "maybe", None, 1):
      with self.subTest(value=value):
        response = self.post_self({"booted": value})
        self.assertEqual(response.status_code, 400)
        self.assertIn("booted", response.json())
        self.assertIsNone(self.last_booted())

  def test_an_empty_body_is_400(self):
    self.assertEqual(self.post_self({}).status_code, 400)

  def test_booted_and_netboot_together(self):
    with self.assertLogs(LOGGER, "INFO") as logs:
      response = self.post_self({"netboot": False, "booted": True})
    self.assertEqual(response.status_code, 200, response.content)
    self.assertEqual(response.json(), {"provision": False, "bootable_nic": "eth0"})
    self.assertEqual([line.split(":", 2)[2] for line in logs.output], [
      f"provisioning: prov-node (10.0.0.20) installed image {self.image.slug}",
      f"provisioning: prov-node (10.0.0.20) booted image {self.image.slug}",
    ])
    self.assertIsNotNone(self.last_booted())

  def test_a_bad_value_changes_nothing(self):
    # everything is checked before anything is changed.
    for body in ({"netboot": "maybe", "booted": True}, {"netboot": False, "booted": False}):
      with self.subTest(body=body):
        self.assertEqual(self.post_self(body).status_code, 400)
        system = System.objects.get(pk=self.system.pk)
        self.assertTrue(system.provision)
        self.assertIsNone(system.last_booted)

  def test_another_key_is_still_403(self):
    self.assertEqual(self.post_self({"booted": True, "hostname": "evil"}).status_code, 403)
    self.assertIsNone(self.last_booted())

  def test_netboot_false_logs_installed(self):
    with self.assertLogs(LOGGER, "INFO") as logs:
      self.post_self({"netboot": False})
    self.assertEqual(logs.output, [f"INFO:{LOGGER}:provisioning: prov-node (10.0.0.20) installed image {self.image.slug}"])
    self.assertIsNone(self.last_booted())

  def test_netboot_true_logs_nothing(self):
    with self.assertNoLogs(LOGGER, "INFO"):
      self.assertEqual(self.post_self({"netboot": True}).status_code, 200)

  def test_a_system_without_an_image(self):
    self.system.systemimage = None
    self.system.save()
    with self.assertLogs(LOGGER, "INFO") as logs:
      self.post_self({"booted": True})
    self.assertEqual(logs.output, [f"INFO:{LOGGER}:provisioning: prov-node (10.0.0.20) booted image (no image)"])

  def test_a_boot_report_queues_no_jobs(self):
    # last_booted is written with update(), so the System save signals (a
    # genders job for every boot) don't fire; netboot still saves normally.
    JobModule.objects.create(slug="libgenders", name="genders")
    with mock.patch("systems.models.requeue_job") as requeue:
      self.post_self({"booted": True})
      requeue.assert_not_called()
      self.post_self({"netboot": False})
      requeue.assert_called()

  def test_a_later_boot_moves_last_booted(self):
    self.post_self({"booted": True})
    first = self.last_booted()
    System.objects.filter(pk=self.system.pk).update(last_booted=first - timedelta(hours=1))
    self.post_self({"booted": True})
    self.assertGreaterEqual(self.last_booted(), first)


class LastBootedAPITests(APITestCase):
  """ #433: last_booted is on the API, read-only. """

  def setUp(self):
    super().setUp()
    self.system = System.objects.create(hostname="api-node", created_by=self.user)

  def test_it_is_read_but_not_written(self):
    self.assertIn("last_booted", self.get_json(f"/systems/{self.system.pk}/").json())
    response = self.client.patch(f"/systems/{self.system.pk}/", json.dumps({"last_booted": "2020-01-01T00:00:00Z"}),
                                 content_type="application/json")
    self.assertEqual(response.status_code, 200, response.content)
    self.assertIsNone(System.objects.get(pk=self.system.pk).last_booted)

  def test_the_admin_shows_it_read_only(self):
    page = self.client.get(f"/admin/systems/system/{self.system.pk}/change/")
    self.assertContains(page, "Last Booted")
    self.assertNotContains(page, 'name="last_booted"')
