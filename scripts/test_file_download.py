import tempfile

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import resolve

from scripts.models import File
from scripts.views import FileDownloadView


@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class FileDownloadTests(TestCase):
  """ /scripts/files/<slug>/ redirects to the current version, without a client needing to know it. """

  def test_download_route_takes_slug(self):
    match = resolve("/scripts/files/motd/")
    self.assertEqual(match.func.view_class, FileDownloadView)
    self.assertEqual(match.kwargs, {"pk": "motd"})

  def test_redirects_to_the_current_version(self):
    f = File.objects.create(name="motd", filename=SimpleUploadedFile("motd.txt", b"hi\n"))
    response = self.client.get(f"/scripts/files/{f.slug}/")
    self.assertRedirects(response, f.filename.url, fetch_redirect_response=False)
    self.assertIn(f"-v{f.version}", response.url)

  def test_unknown_slug_404s(self):
    response = self.client.get("/scripts/files/no-such-file/")
    self.assertEqual(response.status_code, 404)

  def test_redirects_to_the_new_version_after_a_reupload(self):
    f = File.objects.create(name="motd", filename=SimpleUploadedFile("motd.txt", b"hi\n"))
    f.version = 2
    f.filename = SimpleUploadedFile("motd.txt", b"hi again\n")
    f.save()
    response = self.client.get(f"/scripts/files/{f.slug}/")
    self.assertRedirects(response, f.filename.url, fetch_redirect_response=False)
    self.assertIn("-v2", response.url)
