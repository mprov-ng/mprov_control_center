from django.apps import AppConfig


class ScriptsConfig(AppConfig):
    """ The scripts app: scripts, Ansible playbooks, roles and collections, and files. """
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'scripts'
    verbose_name="Config Management"