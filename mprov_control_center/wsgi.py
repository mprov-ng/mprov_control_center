"""
WSGI config for mprov_control_center project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/2.0/howto/deployment/wsgi/
"""

import os

from django.core.wsgi import get_wsgi_application
import dotenv

dotenv_path = os.path.join(os.path.dirname(__file__), '../.env')
dotenv.read_dotenv(dotenv=dotenv_path)
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "mprov_control_center.settings")

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "mprov_control_center.settings")

application = get_wsgi_application()
