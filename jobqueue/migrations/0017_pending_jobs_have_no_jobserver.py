from django.db import migrations

PENDING = 1


def clear_pending_jobservers(apps, schema_editor):
    # A pending job belongs to no job server, so any one can claim it (#296).
    # Jobs reset to pending by a change signal kept the job server that had
    # been running them.
    Job = apps.get_model('jobqueue', 'Job')
    Job.objects.filter(status_id=PENDING).exclude(jobserver=None).update(jobserver=None)


class Migration(migrations.Migration):

    dependencies = [
        ('jobqueue', '0016_jobserveraddress'),
    ]

    operations = [
        migrations.RunPython(clear_pending_jobservers, migrations.RunPython.noop),
    ]
