# Generated by Django 3.2.13 on 2022-05-10 17:02

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('jobqueue', '0003_auto_20220426_1559'),
    ]

    operations = [
        migrations.AddField(
            model_name='jobserver',
            name='port',
            field=models.IntegerField(default=80, verbose_name='Port'),
        ),
    ]
