# Generated by Django 3.2.13 on 2022-07-10 00:15

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('osmanagement', '0008_auto_20220707_1903'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='osrepo',
            name='hosted_by',
        ),
    ]
