# Generated by Django 3.2.12 on 2022-04-07 20:09

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('jobqueue', '0011_jobserver_jobmodules'),
    ]

    operations = [
        migrations.AddField(
            model_name='job',
            name='module',
            field=models.ForeignKey(default='pxe-update', on_delete=django.db.models.deletion.CASCADE, to='jobqueue.jobmodule'),
            preserve_default=False,
        ),
    ]
