# Generated by Django 3.2.13 on 2022-09-21 18:30

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('jobqueue', '0008_alter_jobserver_one_minute_load'),
    ]

    operations = [
        migrations.AlterField(
            model_name='jobserver',
            name='port',
            field=models.IntegerField(default=8080, verbose_name='Port'),
        ),
    ]
