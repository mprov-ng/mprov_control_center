from django.apps import AppConfig


class DisklayoutsConfig(AppConfig):
    """ The disklayouts app: physical disk and software RAID layouts for stateful
    installs. """
    default_auto_field = 'django.db.models.BigAutoField'
    verbose_name = 'System Disk Layouts'
    name = 'disklayouts'
