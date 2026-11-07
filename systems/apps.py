from django.apps import AppConfig


class SystemsConfig(AppConfig):
    """ The systems app: systems, their NICs and BMCs, images, groups, models, locations
    and N.A.D.S. """
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'systems'
    verbose_name = "Systems Inventory"
