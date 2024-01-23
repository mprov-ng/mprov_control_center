# Generated by Django 3.2.23 on 2024-01-23 03:16

import datetime
from django.db import migrations, models
from django.utils.timezone import utc


class Migration(migrations.Migration):

    dependencies = [
        ('jobqueue', '0010_alter_jobserver_address'),
    ]

    operations = [
        migrations.AlterField(
            model_name='job',
            name='create_time',
            field=models.DateTimeField(default=datetime.datetime(2024, 1, 23, 3, 16, 43, 721756, tzinfo=utc), verbose_name='Created Time'),
        ),
        migrations.AlterField(
            model_name='job',
            name='last_update',
            field=models.DateTimeField(blank=True, default=datetime.datetime(2024, 1, 23, 3, 16, 43, 721803, tzinfo=utc), null=True, verbose_name='Last Update'),
        ),
        migrations.AlterField(
            model_name='jobserver',
            name='heartbeat_time',
            field=models.DateTimeField(default=datetime.datetime(2024, 1, 23, 3, 16, 43, 723156, tzinfo=utc), verbose_name='Last Heart Beat'),
        ),
    ]
