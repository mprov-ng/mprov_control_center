from django.apps import AppConfig


class OsmanagementConfig(AppConfig):
    """ The osmanagement app: OS distributions, their repositories and OS types. """
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'osmanagement'
    verbose_name="OS Management"
