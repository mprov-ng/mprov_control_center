# Generated by Django 3.2.12 on 2022-04-01 20:30

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('osmanagement', '0010_alter_osdistro_config_params'),
    ]

    operations = [
        migrations.AlterField(
            model_name='osdistro',
            name='config_params',
            field=models.TextField(blank=True, default='-- # None', null=True, verbose_name='Configuration\nParameters'),
        ),
    ]
