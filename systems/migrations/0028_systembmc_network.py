# Generated by Django 3.2.15 on 2022-10-13 20:56

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('networks', '0012_auto_20220623_1400'),
        ('systems', '0027_alter_system_disks'),
    ]

    operations = [
        migrations.AddField(
            model_name='systembmc',
            name='network',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='networks.network', verbose_name='Network'),
        ),
    ]
