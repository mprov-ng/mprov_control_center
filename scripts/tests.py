from django.test import SimpleTestCase
from django.urls import resolve

from scripts.views import ScriptAPIView


class ScriptURLTests(SimpleTestCase):
  """ /scripts/<pk>/ takes a script slug. """

  def test_detail_route_takes_slug(self):
    match = resolve("/scripts/extra_packagessh/")
    self.assertEqual(match.func.view_class, ScriptAPIView)
    self.assertEqual(match.kwargs, {"pk": "extra_packagessh"})
