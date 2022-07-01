# Generated by Django 3.2.13 on 2022-07-01 14:36

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('jobqueue', '0007_jobserver_network'),
    ]

    operations = [
        migrations.AlterField(
            model_name='jobserver',
            name='one_minute_load',
            field=models.FloatField(default=0.0, null=True, verbose_name='1 Minute Load Avg.'),
        ),
    ]