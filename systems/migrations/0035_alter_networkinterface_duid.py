# Generated by Django 3.2.16 on 2022-11-06 17:32

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('systems', '0034_networkinterface_duid'),
    ]

    operations = [
        migrations.AlterField(
            model_name='networkinterface',
            name='duid',
            field=models.CharField(blank=True, default='', max_length=100, null=True, verbose_name='DUID'),
        ),
    ]
