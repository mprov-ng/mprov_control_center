# Generated by Django 3.2.13 on 2022-08-04 14:10

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('systems', '0022_auto_20220804_1346'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='system',
            name='bootdisk',
        ),
    ]