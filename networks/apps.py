from django.apps import AppConfig


class NetworksConfig(AppConfig):
    """ The networks app: networks, network types, switches and switch ports. """
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'networks'
    verbose_name = "Network Management"

    def ready(self):
        # the switch port <-> NIC network sync (#578)
        from networks import port_sync  # noqa: F401
