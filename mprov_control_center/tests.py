import os
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