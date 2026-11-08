""" A bmc-rotate job that finishes without reporting a result (#486). """
from django.db.models.signals import post_save
from django.dispatch import receiver


@receiver(post_save, sender='jobqueue.Job')
def bmc_job_ended(sender, instance, **kwargs):
    from bmcrotate.logic import FAILED, MODULE, SUCCESS, job_ended
    if instance.module_id == MODULE and instance.status_id in (FAILED, SUCCESS):
        job_ended(instance)
