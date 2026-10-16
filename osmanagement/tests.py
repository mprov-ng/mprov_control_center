from bs4 import BeautifulSoup
from django.test import TestCase

from osmanagement.models import OSRepo


class OSRepoListTests(TestCase):
  """ The unauthenticated /osrepos/ page lists repos as HTML, escaping admin-set values. """

  def test_repo_name_and_url_are_escaped(self):
    OSRepo.objects.create(name="<script>alert(1)</script>", repo_package_url="http://repo/'onmouseover='alert(2)")
    OSRepo.objects.create(name="<b>managed</b>", repo_package_url="http://unused/", managed=True)
    response = self.client.get("/osrepos/")
    self.assertEqual(response.status_code, 200)
    content = response.content.decode()
    self.assertNotIn("<script>alert(1)", content)
    self.assertNotIn("<b>managed</b>", content)
    links = BeautifulSoup(content, features="html.parser").select("ul li a")
    self.assertEqual([a.get_text() for a in links], ["<b>managed</b>", "<script>alert(1)</script>"])
    self.assertEqual(links[1]["href"], "http://repo/'onmouseover='alert(2)")
    self.assertNotIn("onmouseover", links[1].attrs)
