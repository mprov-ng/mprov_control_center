from django.apps import AppConfig


class BmcrotateConfig(AppConfig):
    """ Changing BMC credentials on the BMCs themselves (#486). """
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'bmcrotate'
    verbose_name = "BMC Credential Changes"

    def ready(self):
        from bmcrotate import signals  # noqa: F401
