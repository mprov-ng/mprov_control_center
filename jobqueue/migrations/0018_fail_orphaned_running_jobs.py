from django.db import migrations
from django.utils import timezone

RUNNING, ERROR = 2, 3


def fail_orphaned_running_jobs(apps, schema_editor):
    # Jobs left RUNNING by a job server the mPCC deleted: nothing will ever
    # finish them (#409).
    Job = apps.get_model('jobqueue', 'Job')
    Job.objects.filter(status_id=RUNNING, jobserver=None).update(status_id=ERROR, end_time=timezone.now())


class Migration(migrations.Migration):

    dependencies = [
        ('jobqueue', '0017_pending_jobs_have_no_jobserver'),
    ]

    operations = [
        migrations.RunPython(fail_orphaned_running_jobs, migrations.RunPython.noop),
    ]
