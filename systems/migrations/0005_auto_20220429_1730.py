# Generated by Django 3.2.12 on 2022-04-29 17:30

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('scripts', '0003_alter_script_dependson'),
        ('systems', '0004_rename_config_parameters_system_config_params'),
    ]

    operations = [
        migrations.AddField(
            model_name='system',
            name='scripts',
            field=models.ManyToManyField(to='scripts.Script'),
        ),
        migrations.AddField(
            model_name='systemgroup',
            name='scripts',
            field=models.ManyToManyField(to='scripts.Script'),
        ),
    ]
