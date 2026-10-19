from django.test import TestCase


class OSRepoRedirectTests(TestCase):
  """ /osrepos/<pk>/ redirects to a job server, or 404s. """

  def test_unknown_repo_is_404(self):
    self.assertEqual(self.client.get("/osrepos/999/").status_code, 404)
    self.assertEqual(self.client.get("/osrepos/999/repodata/repomd.xml").status_code, 404)
