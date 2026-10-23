from django.contrib import admin
from django.contrib.auth.models import User
from django.test import RequestFactory, TestCase

from scripts.models import AnsibleCollection, AnsiblePlaybook, AnsibleRole, File, Script


class VersionWidgetTests(TestCase):
  """ The version input steps from min=1, so the spinner arrows work (#172). """

  def test_version_min_is_1(self):
    request = RequestFactory().get("/")
    request.user = User(is_superuser=True, is_staff=True, is_active=True)
    for model in (Script, File, AnsiblePlaybook, AnsibleRole, AnsibleCollection):
      with self.subTest(model=model.__name__):
        form = admin.site._registry[model].get_form(request)
        self.assertEqual(form.base_fields["version"].widget.attrs["min"], 1)
