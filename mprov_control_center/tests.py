import os
from io import StringIO
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.contrib.auth.password_validation import validate_password
from django.test import TestCase


class MProvConfigTest(TestCase):

  def test_secret_key_strength(self):
    # settings.py reads it from the environment; Django refuses to return an
    # empty settings.SECRET_KEY, so check the environment directly.
    SECRET_KEY = os.environ.get('SECRET_KEY')
    if not SECRET_KEY:
      self.fail("SECRET_KEY is not set")
    try:
      validate_password(SECRET_KEY)
    except ValidationError as e:
      self.fail(f'Weak Secret Key {e.messages}')


class MigrationsTest(TestCase):

  def test_no_missing_migrations(self):
    """ Every model change has a migration committed for it. """
    out = StringIO()
    try:
      call_command('makemigrations', '--check', '--dry-run', stdout=out, stderr=StringIO())
    except SystemExit:
      self.fail(f"Missing migrations; run 'python manage.py makemigrations':\n{out.getvalue()}")


class DataModelViewTests(TestCase):
  """ /datamodel/ describes the fields of a model. """

  def test_field_type_key(self):
    response = self.client.get("/datamodel/", {"model": "jobqueue.models.JobModule"})
    self.assertEqual(response.status_code, 200)
    self.assertEqual(response.json()["fields"]["name"], {"type": "string", "required": True})

  def test_unknown_model_is_404(self):
    response = self.client.get("/datamodel/", {"model": "nope.models.Nope"})
    self.assertEqual(response.status_code, 404)
    self.assertEqual(response.json(), {"error": "Unknown Model Requested"})


class AdminBaseTemplateTests(TestCase):
  """ templates/admin/base.html adds mProv's admin JS and CSS to every admin page. """

  def test_kept_when_a_child_overrides_extrahead(self):
    from django.contrib.auth.models import User
    from django.template import engines
    from django.test import RequestFactory
    request = RequestFactory().get("/admin/")
    request.user = User.objects.create_superuser("admin", "admin@example.com", "password")
    template = engines["django"].from_string(
      '{% extends "admin/base.html" %}{% block extrahead %}<meta name="child">{% endblock %}')
    html = template.render({}, request)
    self.assertIn('<meta name="child">', html)
    self.assertIn("admin/js/job_notifications.js", html)
    self.assertIn("/static/css/mprov.css", html)
