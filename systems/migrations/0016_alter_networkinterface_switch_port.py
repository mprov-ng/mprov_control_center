# Generated by Django 3.2.13 on 2022-05-17 18:09

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('networks', '0008_auto_20220504_1844'),
        ('systems', '0015_networkinterface_bootable'),
    ]

    operations = [
        migrations.AlterField(
            model_name='networkinterface',
            name='switch_port',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='networks.switchport', unique=True, verbose_name='Switch Port'),
        ),
    ]
