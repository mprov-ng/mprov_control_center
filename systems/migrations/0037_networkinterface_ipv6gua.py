# Generated by Django 3.2.16 on 2022-11-11 16:54

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('systems', '0036_remove_networkinterface_duid'),
    ]

    operations = [
        migrations.AddField(
            model_name='networkinterface',
            name='ipv6gua',
            field=models.GenericIPAddressField(blank=True, null=True, verbose_name='IPv6 SLACC GUA'),
        ),
    ]
