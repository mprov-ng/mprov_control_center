from django.apps import AppConfig


class JobqueueConfig(AppConfig):
    """ The jobqueue app: jobs, job modules and the job servers that run them. """
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'jobqueue'
    verbose_name="mProv Job Management"

    def ready(self):
        import jobqueue.signals  # noqa: F401 (registers the signal handlers)
