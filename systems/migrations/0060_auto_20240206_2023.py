# Generated by Django 3.2.23 on 2024-02-06 20:23

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('systems', '0059_rename_gateway_networkinterface_isgateway'),
    ]

    operations = [
        migrations.AddField(
            model_name='nadssystem',
            name='model',
            field=models.CharField(blank=True, max_length=1024, null=True, verbose_name='Detected Model'),
        ),
        migrations.AddField(
            model_name='nadssystem',
            name='port',
            field=models.CharField(blank=True, max_length=1024, null=True, verbose_name='Detected Port'),
        ),
        migrations.AddField(
            model_name='nadssystem',
            name='switch',
            field=models.CharField(blank=True, max_length=1024, null=True, verbose_name='Detected Switch'),
        ),
        migrations.AddField(
            model_name='nadssystem',
            name='vendor',
            field=models.CharField(blank=True, max_length=1024, null=True, verbose_name='Detected Vendor'),
        ),
    ]
