# Generated by Django 3.2.12 on 2022-05-02 21:14

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('systems', '0010_system_systemimage'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='system',
            name='osdistro',
        ),
        migrations.RemoveField(
            model_name='system',
            name='osrepos',
        ),
    ]