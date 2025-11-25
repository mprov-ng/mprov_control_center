from django.apps import AppConfig


class JobqueueConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'jobqueue'
    verbose_name="mProv Job Management"

    def ready(self):
        import jobqueue.signals
