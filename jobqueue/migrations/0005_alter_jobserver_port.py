# Generated by Django 3.2.13 on 2022-05-13 14:49

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('jobqueue', '0004_jobserver_port'),
    ]

    operations = [
        migrations.AlterField(
            model_name='jobserver',
            name='port',
            field=models.IntegerField(default=80, null=True, verbose_name='Port'),
        ),
    ]