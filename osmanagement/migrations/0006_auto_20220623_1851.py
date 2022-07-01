# Generated by Django 3.2.13 on 2022-06-23 18:51

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('osmanagement', '0005_alter_osdistro_config_params'),
    ]

    operations = [
        migrations.AddField(
            model_name='osdistro',
            name='initial_mods',
            field=models.CharField(default='e1000,tg3', help_text='Comma separated list of modules to load.', max_length=255),
        ),
        migrations.AddField(
            model_name='osdistro',
            name='prov_interface',
            field=models.CharField(default='eth0', help_text='Interface name to provision over.', max_length=255),
        ),
        migrations.AddField(
            model_name='osdistro',
            name='tmpfs_root_size',
            field=models.IntegerField(default=8, help_text='Size of the root tmpfs filesystem in Gibabytes'),
        ),
    ]