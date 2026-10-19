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
