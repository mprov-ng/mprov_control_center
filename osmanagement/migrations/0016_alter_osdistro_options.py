# Generated by Django 3.2.15 on 2022-10-20 15:12

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('osmanagement', '0015_remove_osrepo_osdistro'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='osdistro',
            options={'ordering': ['name'], 'verbose_name': 'OS Distribution', 'verbose_name_plural': 'OS Distributions'},
        ),
    ]
