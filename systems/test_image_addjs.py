from django.contrib.auth.models import User
from django.test import TestCase

from systems.models import SystemImage


class SystemImageAddJobserverTests(TestCase):
  """ PATCH /systemimages/<pk>/?addjs adds job servers to the image instead of replacing them. """

  def setUp(self):
    from jobqueue.models import JobServer
    self.user = User.objects.create_superuser("admin", "admin@example.com", "password")
    self.client.force_login(self.user)
    self.image = SystemImage.objects.create(name="compute", created_by=self.user, needs_rebuild=False)
    self.js1, self.js2, self.js3 = (JobServer.objects.create(name=f"js{i}") for i in range(1, 4))
    self.image.jobservers.add(self.js1)

  def addjs(self, jobservers):
    import json
    return self.client.patch(f"/systemimages/{self.image.pk}/?addjs", json.dumps({"jobservers": jobservers}),
                             content_type="application/json")

  def jobserver_ids(self):
    return sorted(self.image.jobservers.values_list("id", flat=True))

  def test_add_a_list(self):
    self.assertEqual(self.addjs([self.js2.id, self.js3.id]).status_code, 200)
    self.assertEqual(self.jobserver_ids(), [self.js1.id, self.js2.id, self.js3.id])

  def test_add_one(self):
    self.assertEqual(self.addjs(self.js2.id).status_code, 200)
    self.assertEqual(self.jobserver_ids(), [self.js1.id, self.js2.id])
