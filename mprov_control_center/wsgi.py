import os

from django.core.wsgi import get_wsgi_application
import dotenv

dotenv_path = os.path.join(os.path.dirname(__file__), '../.env')
dotenv.read_dotenv(dotenv=dotenv_path)
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "mprov_control_center.settings")

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "mprov_control_center.settings")

application = get_wsgi_application()
