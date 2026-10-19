import datetime

from django.utils import timezone

from common.testing import APITestCase
from jobqueue.models import JobServer


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
