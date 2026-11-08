from django.apps import AppConfig


class SystemsConfig(AppConfig):
    """ The systems app: systems, their NICs and BMCs, images, groups, models, locations
    and N.A.D.S. """
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'systems'
    verbose_name = "Systems Inventory"

    def ready(self):
        # Before any migration runs, bring tables an older release created in
        # another collation to the database's utf8mb4 one, or the first new
        # foreign key to one of their string keys fails (#526).  Sent once per
        # migrate for each app with models; systems always has them.
        from django.db.models.signals import pre_migrate
        from common.dbcharset import normalize_before_migrate
        pre_migrate.connect(normalize_before_migrate, sender=self, dispatch_uid="mprov-normalize-charset")
