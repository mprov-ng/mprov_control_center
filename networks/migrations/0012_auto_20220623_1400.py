# Generated by Django 3.2.13 on 2022-06-23 14:00

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('networks', '0011_auto_20220618_0029'),
    ]

    operations = [
        migrations.AlterField(
            model_name='network',
            name='dhcpend',
            field=models.GenericIPAddressField(blank=True, null=True, verbose_name='DHCP Range End'),
        ),
        migrations.AlterField(
            model_name='network',
            name='dhcpstart',
            field=models.GenericIPAddressField(blank=True, null=True, verbose_name='DHCP Range Start'),
        ),
        migrations.AlterField(
            model_name='network',
            name='domain',
            field=models.CharField(blank=True, max_length=255, verbose_name='Domain Name'),
        ),
        migrations.AlterField(
            model_name='network',
            name='isbootable',
            field=models.BooleanField(default=False, verbose_name='Enable network booting?'),
        ),
        migrations.AlterField(
            model_name='network',
            name='isdhcp',
            field=models.BooleanField(default=False, verbose_name='Enable DHCP Server?'),
        ),
        migrations.AlterField(
            model_name='network',
            name='managedns',
            field=models.BooleanField(default=False, verbose_name='Manage DNS for network?'),
        ),
        migrations.AlterField(
            model_name='network',
            name='nameserver1',
            field=models.GenericIPAddressField(blank=True, null=True, verbose_name='Primary Nameserver'),
        ),
    ]
