# Generated by Django 3.2.12 on 2022-04-01 19:40

from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('systems', '0010_alter_system_config_parameters'),
    ]

    operations = [
        migrations.AlterField(
            model_name='system',
            name='config_parameters',
            field=models.TextField(blank=True, default='-- #Inherit from System Group or Distrubtion.', null=True, verbose_name='Configuration\nParameters'),
        ),
        migrations.AlterField(
            model_name='system',
            name='created_by',
            field=models.ForeignKey(on_delete=models.SET(1), to=settings.AUTH_USER_MODEL, verbose_name='Created By'),
        ),
    ]
