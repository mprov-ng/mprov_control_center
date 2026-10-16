import os
from io import StringIO
from django.core.management import call_command
from django.contrib.auth.password_validation import validate_password
from django.test import TestCase


class MProvConfigTest(TestCase):

  def test_secret_key_strength(self):
    SECRET_KEY = os.environ.get('SECRET_KEY')
    try:
      is_strong = validate_password(SECRET_KEY)
    except Exception as e:
      msg = f'Weak Secret Key {e.messages}'
      self.fail()


class MigrationsTest(TestCase):

  def test_no_missing_migrations(self):
    """ Every model change has a migration committed for it. """
    out = StringIO()
    try:
      call_command('makemigrations', '--check', '--dry-run', stdout=out, stderr=StringIO())
    except SystemExit:
      self.fail(f"Missing migrations; run 'python manage.py makemigrations':\n{out.getvalue()}")
