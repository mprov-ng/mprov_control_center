# Generated by Django 3.2.22 on 2025-01-09 17:06

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('networks', '0017_alter_network_vlan'),
    ]

    operations = [
        migrations.AlterField(
            model_name='network',
            name='vlan',
            field=models.IntegerField(default=1),
        ),
    ]
