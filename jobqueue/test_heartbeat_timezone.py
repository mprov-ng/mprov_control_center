import json
from datetime import timedelta
from unittest import mock

from django.test import override_settings
from django.utils import timezone

from common.testing import APITestCase
from jobqueue.models import JobServer


class HeartbeatTimezoneTests(APITestCase):
  """ JobServer.heartbeat_time is always timezone-aware UTC, regardless of the
  server OS's local timezone (#153): a naive datetime.now() used to be mislabeled
  with Django's configured TIME_ZONE, shifting it by the OS/TIME_ZONE offset. """

  def post(self, data):
    return self.client.post("/jobservers/", json.dumps(data), content_type="application/json")

  @override_settings(TIME_ZONE="America/New_York")
  def test_registration_sets_an_aware_heartbeat_close_to_now(self):
    response = self.post({"name": "js1", "address": "10.0.0.1", "one_minute_load": 0.5, "jobmodules": []})
    self.assertEqual(response.status_code, 200)
    server = JobServer.objects.get(name="js1")
    self.assertTrue(timezone.is_aware(server.heartbeat_time))
    self.assertLess(abs((timezone.now() - server.heartbeat_time).total_seconds()), 5)

  def test_stale_cleanup_uses_an_aware_cutoff_regardless_of_os_time(self):
    stale = JobServer.objects.create(name="stale", heartbeat_time=timezone.now() - timedelta(seconds=90))
    fresh = JobServer.objects.create(name="fresh", heartbeat_time=timezone.now())
    # Force the save() path's periodic stale-sweep to run (it only runs on a :00 second).
    with mock.patch("jobqueue.models.time.time", return_value=0.0):
      fresh.save()
    self.assertFalse(JobServer.objects.filter(pk=stale.pk).exists())
    self.assertTrue(JobServer.objects.filter(pk=fresh.pk).exists())
