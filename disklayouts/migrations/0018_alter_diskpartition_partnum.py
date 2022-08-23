# Generated by Django 3.2.13 on 2022-08-23 18:21

import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('disklayouts', '0017_alter_diskpartition_partnum'),
    ]

    operations = [
        migrations.AlterField(
            model_name='diskpartition',
            name='partnum',
            field=models.PositiveIntegerField(default=0, validators=[django.core.validators.MinValueValidator(1)], verbose_name='Part. Number'),
        ),
    ]
