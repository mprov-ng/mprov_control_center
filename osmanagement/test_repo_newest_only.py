import json

from django.contrib.auth.models import User
from django.test import TestCase

from osmanagement.models import OSDistro, OSRepo, OSType


class RepoNewestOnlyTests(TestCase):
  """ newest_only: the per-repo "mirror only the newest packages" setting the job server's repo-update reads (#156). """

  def setUp(self):
    self.client.force_login(User.objects.create_superuser("admin", "admin@example.com", "password"))

  def test_on_by_default(self):
    repo = OSRepo.objects.create(name="BaseOS", repo_package_url="http://mirror/")
    self.assertTrue(repo.newest_only)

  def test_repo_get_returns_it(self):
    # repo-update reads the repo from GET /repos/<id>/.
    repo = OSRepo.objects.create(name="BaseOS", repo_package_url="http://mirror/")
    response = self.client.get(f"/repos/{repo.id}/", CONTENT_TYPE="application/json")
    self.assertEqual(response.status_code, 200, response.content)
    self.assertIs(response.json()["newest_only"], True)

  def test_patch_turns_it_off(self):
    repo = OSRepo.objects.create(name="BaseOS", repo_package_url="http://mirror/")
    response = self.client.patch(f"/repos/{repo.id}/", json.dumps({"newest_only": False}), content_type="application/json")
    self.assertEqual(response.status_code, 200, response.content)
    repo.refresh_from_db()
    self.assertFalse(repo.newest_only)

  def test_post_without_it_defaults_on(self):
    response = self.client.post("/repos/", json.dumps({"name": "extras", "repo_package_url": "http://mirror/extras/"}), content_type="application/json")
    self.assertEqual(response.status_code, 201, response.content)
    self.assertIs(response.json()["newest_only"], True)

  def test_list_filters_by_it(self):
    OSRepo.objects.create(name="all", repo_package_url="http://mirror/all/", newest_only=False)
    OSRepo.objects.create(name="newest", repo_package_url="http://mirror/newest/")
    response = self.client.get("/repos/?newest_only=False", CONTENT_TYPE="application/json")
    self.assertEqual(response.status_code, 200, response.content)
    self.assertEqual([r["name"] for r in response.json()], ["all"])

  def test_generated_distro_repos_are_newest_only(self):
    ostype = OSType.objects.create(slug="rhel", name="Yum/DNF Based Linux")
    OSDistro.objects.create(name="Rocky 9", vendor="Rocky", version="9", distType=ostype, distArch="x86_64",
                            update=True, managed=True, baseurl="https://download.rockylinux.org/pub/rocky/9")
    # BaseOS, AppStream, extras, CRB and EPEL.
    self.assertEqual(OSRepo.objects.count(), 5)
    self.assertFalse(OSRepo.objects.filter(newest_only=False).exists())
