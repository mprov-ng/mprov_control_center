# Generated by Django 3.2.15 on 2022-10-17 15:15

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('systems', '0029_auto_20221017_1513'),
    ]

    operations = [
        migrations.AlterField(
            model_name='system',
            name='initial_mods',
            field=models.CharField(default='', help_text='Comma separated list of modules to load.', max_length=255),
        ),
        migrations.AlterField(
            model_name='system',
            name='prov_interface',
            field=models.CharField(default='', help_text='Interface name to provision over.', max_length=255),
        ),
        migrations.AlterField(
            model_name='system',
            name='tmpfs_root_size',
            field=models.IntegerField(default=0, help_text='Size of the root tmpfs filesystem in Gibabytes, 0 inherits from parent Group/Distro'),
        ),
        migrations.AlterField(
            model_name='systemgroup',
            name='initial_mods',
            field=models.CharField(default='', help_text='Comma separated list of modules to load.', max_length=255),
        ),
        migrations.AlterField(
            model_name='systemgroup',
            name='prov_interface',
            field=models.CharField(default='', help_text='Interface name to provision over.', max_length=255),
        ),
        migrations.AlterField(
            model_name='systemgroup',
            name='tmpfs_root_size',
            field=models.IntegerField(default=0, help_text='Size of the root tmpfs filesystem in Gibabytes, 0 inherits from parent Group/Distro'),
        ),
    ]
