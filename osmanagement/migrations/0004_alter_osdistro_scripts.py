# Generated by Django 3.2.12 on 2022-04-29 17:31

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('scripts', '0003_alter_script_dependson'),
        ('osmanagement', '0003_osdistro_scripts'),
    ]

    operations = [
        migrations.AlterField(
            model_name='osdistro',
            name='scripts',
            field=models.ManyToManyField(blank=True, to='scripts.Script'),
        ),
    ]
