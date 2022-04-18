# Generated by Django 3.2.12 on 2022-03-30 20:42

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('networks', '0004_alter_switch_options'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('systems', '0002_auto_20220330_2030'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='systemgroup',
            name='parent_id',
        ),
        migrations.AlterField(
            model_name='networkinterface',
            name='ipaddress',
            field=models.GenericIPAddressField(verbose_name='IP Address '),
        ),
        migrations.AlterField(
            model_name='networkinterface',
            name='mac',
            field=models.CharField(max_length=100, verbose_name='MAC Address'),
        ),
        migrations.AlterField(
            model_name='networkinterface',
            name='name',
            field=models.CharField(max_length=120, verbose_name='Interface Name(eg. eth0)'),
        ),
        migrations.AlterField(
            model_name='networkinterface',
            name='switch_port',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.DO_NOTHING, to='networks.switchport', verbose_name='Switch Port'),
        ),
        migrations.AlterField(
            model_name='system',
            name='created_by',
            field=models.ForeignKey(on_delete=django.db.models.deletion.DO_NOTHING, to=settings.AUTH_USER_MODEL, verbose_name='Created By'),
        ),
        migrations.AlterField(
            model_name='system',
            name='domainname',
            field=models.CharField(max_length=255, verbose_name='Domain Name'),
        ),
        migrations.AlterField(
            model_name='system',
            name='hostname',
            field=models.CharField(max_length=255, verbose_name='Host Name'),
        ),
        migrations.AlterField(
            model_name='system',
            name='systemgroups',
            field=models.ManyToManyField(to='systems.SystemGroup', verbose_name='System Groups'),
        ),
        migrations.AlterField(
            model_name='system',
            name='timestamp',
            field=models.DateTimeField(auto_now_add=True, verbose_name='Created'),
        ),
        migrations.AlterField(
            model_name='system',
            name='updated',
            field=models.DateTimeField(auto_now=True, verbose_name='Lasted Updated'),
        ),
        migrations.AlterField(
            model_name='systemgroup',
            name='extra_fields',
            field=models.TextField(blank=True, default='-- # Inherit', verbose_name='Extra Fields'),
        ),
    ]
