# Generated by Django 3.2.20 on 2023-09-13 19:59

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('networks', '0014_alter_switchport_networks'),
        ('systems', '0048_auto_20230518_1436'),
    ]

    operations = [
        migrations.AddField(
            model_name='networkinterface',
            name='network',
            field=models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='networks.network', verbose_name='Network'),
        ),
    ]
