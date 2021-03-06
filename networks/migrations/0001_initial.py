# Generated by Django 3.2.12 on 2022-04-25 20:41

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Network',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=120)),
                ('vlan', models.CharField(default='default', max_length=100)),
                ('subnet', models.GenericIPAddressField(default='0.0.0.0')),
                ('netmask', models.IntegerField(choices=[(1, 1), (2, 2), (3, 3), (4, 4), (5, 5), (6, 6), (7, 7), (8, 8), (9, 9), (10, 10), (11, 11), (12, 12), (13, 13), (14, 14), (15, 15), (16, 16), (17, 17), (18, 18), (19, 19), (20, 20), (21, 21), (22, 22), (23, 23), (24, 24), (25, 25), (26, 26), (27, 27), (28, 28), (29, 29), (30, 30), (31, 31)], verbose_name='CIDR Mask')),
            ],
        ),
        migrations.CreateModel(
            name='NetworkType',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=120)),
                ('description', models.TextField(blank=True, null=True)),
            ],
            options={
                'verbose_name': 'Network Type',
            },
        ),
        migrations.CreateModel(
            name='Switch',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('hostname', models.CharField(max_length=255, verbose_name='Host Name')),
                ('domainname', models.CharField(max_length=255, verbose_name='Domain Name')),
                ('timestamp', models.DateTimeField(auto_now_add=True, verbose_name='Created')),
                ('updated', models.DateTimeField(auto_now=True, verbose_name='Last Updated')),
                ('mgmt_ip', models.GenericIPAddressField(verbose_name='Management IP')),
                ('mgmt_mac', models.CharField(max_length=100, verbose_name='Management MAC')),
                ('created_by', models.ForeignKey(on_delete=django.db.models.deletion.DO_NOTHING, to=settings.AUTH_USER_MODEL, verbose_name='Created By')),
                ('network', models.ForeignKey(on_delete=django.db.models.deletion.DO_NOTHING, to='networks.network', verbose_name='Management\nNetwork')),
            ],
            options={
                'verbose_name': 'Switch',
                'verbose_name_plural': 'Switches',
            },
        ),
        migrations.CreateModel(
            name='SwitchPort',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=100)),
                ('networks', models.ManyToManyField(to='networks.Network', verbose_name='Networks')),
                ('switch', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='networks.switch')),
            ],
            options={
                'verbose_name': 'Switch Port',
            },
        ),
        migrations.AddField(
            model_name='network',
            name='net_type',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='networks.networktype', verbose_name='Network Type'),
        ),
    ]
