# Generated by Django 3.2.23 on 2024-01-23 03:18

from django.db import migrations, models
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ('jobqueue', '0011_auto_20240123_0316'),
    ]

    operations = [
        migrations.AlterField(
            model_name='job',
            name='create_time',
            field=models.DateTimeField(default=django.utils.timezone.now, verbose_name='Created Time'),
        ),
        migrations.AlterField(
            model_name='job',
            name='last_update',
            field=models.DateTimeField(blank=True, default=django.utils.timezone.now, null=True, verbose_name='Last Update'),
        ),
        migrations.AlterField(
            model_name='jobserver',
            name='heartbeat_time',
            field=models.DateTimeField(default=django.utils.timezone.now, verbose_name='Last Heart Beat'),
        ),
    ]
