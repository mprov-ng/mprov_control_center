from django.db import migrations, models


def drop_long_addresses(apps, schema_editor):
    """ Delete any job server address over 255 characters, which the shorter
    column can't hold (a strict-mode ALTER would fail on it).  None is
    expected: job servers send interface addresses.  Addresses are heartbeat
    state, re-sent by the job server when it next registers. """
    JobServerAddress = apps.get_model('jobqueue', 'JobServerAddress')
    long_ids = [a.pk for a in JobServerAddress.objects.only('pk', 'address') if len(a.address) > 255]
    JobServerAddress.objects.filter(pk__in=long_ids).delete()


class Migration(migrations.Migration):
    """ Shrink JobServerAddress.address from 1024 to 255 on sites that ran
    0016 before it was changed to create it at 255 (#527): the unique
    (jobserver, address) key at 1024 is over MySQL's 3072-byte key limit.
    On a database that ran the current 0016 this changes nothing. """

    dependencies = [
        ('jobqueue', '0020_job_last_update_auto_now'),
    ]

    operations = [
        migrations.RunPython(drop_long_addresses, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='jobserveraddress',
            name='address',
            field=models.CharField(max_length=255),
        ),
    ]
