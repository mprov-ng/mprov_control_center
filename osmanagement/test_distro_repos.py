from django.test import TestCase

from osmanagement.models import OSDistro, OSRepo


class OSDistroCreateReposTests(TestCase):
  """ Saving a distro with update set creates its repos under the base URL. """

  def test_trailing_slash_is_stripped(self):
    OSDistro.objects.create(name="Rocky 9", vendor="Rocky", version="9", update=True,
                            baseurl="http://mirror/rocky/9/")
    self.assertEqual(OSRepo.objects.get(name="BaseOS-9").repo_package_url,
                     "http://mirror/rocky/9/BaseOS/x86_64/os/")
