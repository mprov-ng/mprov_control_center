from django.core.management import call_command
from django.test import TestCase

from jobqueue.models import Job
from osmanagement.models import OSDistro, OSRepo

ROCKY9 = "https://download.rockylinux.org/pub/rocky/9"


class DefaultDistroFixtureTests(TestCase):
  """ A fresh install's distro is Rocky Linux 9 (#495), and generates its repos
  from the fixture, unmirrored (#356, #346). """

  def setUp(self):
    call_command("loaddata", "osmanagement/fixtures/osmanagement.yaml", verbosity=0)
    self.distro = OSDistro.objects.get(pk=1)

  def test_repos_are_generated(self):
    self.assertEqual((self.distro.name, self.distro.version), ("Rocky Linux 9", "9"))
    self.assertEqual(self.distro.baserepo.name, "BaseOS-9")
    self.assertEqual(self.distro.baserepo.repo_package_url, f"{ROCKY9}/BaseOS/x86_64/os/")
    self.assertEqual(
      {r.name: r.repo_package_url for r in self.distro.osrepos.all()},
      {
        "AppStream-9": f"{ROCKY9}/AppStream/x86_64/os/",
        "extras-9": f"{ROCKY9}/extras/x86_64/os/",
        "CRB-9": f"{ROCKY9}/CRB/x86_64/os/",
        "EPEL-9": "https://dl.fedoraproject.org/pub/epel/9/Everything/x86_64/",
      },
    )

  def test_repos_are_not_mirrored(self):
    self.assertEqual(OSRepo.objects.count(), 5)
    self.assertFalse(OSRepo.objects.filter(managed=True).exists())
    self.assertFalse(Job.objects.exists())

  def test_no_rocky_8(self):
    self.assertFalse(OSDistro.objects.filter(version="8").exists())

  def test_generate_is_cleared(self):
    self.assertFalse(self.distro.update)
    self.assertFalse(self.distro.managed)
