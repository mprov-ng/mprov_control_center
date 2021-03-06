# Generated by Django 3.2.12 on 2022-04-25 20:41

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('osmanagement', '0001_initial'),
        ('networks', '0001_initial'),
        ('jobqueue', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='SystemGroup',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=255)),
                ('conf_params', models.TextField(blank=True, default='-- # Inherit from OS', verbose_name='Configuration Parameters')),
            ],
            options={
                'verbose_name': 'System Group',
                'verbose_name_plural': 'System Groups',
                'ordering': ['name'],
            },
        ),
        migrations.CreateModel(
            name='SystemImage',
            fields=[
                ('name', models.CharField(max_length=255, verbose_name='Image Name')),
                ('slug', models.SlugField(editable=False, max_length=255, primary_key=True, serialize=False, unique=True, verbose_name='Image ID')),
                ('timestamp', models.DateTimeField(auto_now_add=True, verbose_name='Created')),
                ('updated', models.DateTimeField(auto_now=True, verbose_name='Lasted Updated')),
                ('needs_rebuild', models.BooleanField(default=True, verbose_name='Rebuild Image?')),
                ('version', models.BigIntegerField(default=1, verbose_name='Image Version')),
                ('config_parameters', models.TextField(blank=True, default='-- #Inherit from System Group or Distrubtion.', null=True, verbose_name='Configuration\nParameters')),
                ('created_by', models.ForeignKey(on_delete=models.SET(1), to=settings.AUTH_USER_MODEL, verbose_name='Created By')),
                ('jobservers', models.ManyToManyField(blank=True, to='jobqueue.JobServer', verbose_name='Hosted By')),
                ('osdistro', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='osmanagement.osdistro', verbose_name='OS Distrubution')),
                ('osrepos', models.ManyToManyField(blank=True, to='osmanagement.OSRepo', verbose_name='OS Repositories')),
                ('systemgroups', models.ManyToManyField(blank=True, to='systems.SystemGroup', verbose_name='System Groups')),
            ],
            options={
                'verbose_name': 'System Image',
                'ordering': ['name'],
            },
        ),
        migrations.CreateModel(
            name='System',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('hostname', models.CharField(max_length=255, verbose_name='Host Name')),
                ('domainname', models.CharField(max_length=255, verbose_name='Domain Name')),
                ('timestamp', models.DateTimeField(auto_now_add=True, verbose_name='Created')),
                ('updated', models.DateTimeField(auto_now=True, verbose_name='Lasted Updated')),
                ('config_parameters', models.TextField(blank=True, default='-- #Inherit from System Group or Distrubtion.', null=True, verbose_name='Configuration\nParameters')),
                ('created_by', models.ForeignKey(on_delete=models.SET(1), to=settings.AUTH_USER_MODEL, verbose_name='Created By')),
                ('osdistro', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='osmanagement.osdistro', verbose_name='OS Distrubution')),
                ('osrepos', models.ManyToManyField(blank=True, to='osmanagement.OSRepo', verbose_name='OS Repositories')),
                ('systemgroups', models.ManyToManyField(blank=True, to='systems.SystemGroup', verbose_name='System Groups')),
            ],
            options={
                'verbose_name': 'Systems',
                'verbose_name_plural': 'Systems',
                'ordering': ['hostname'],
            },
        ),
        migrations.CreateModel(
            name='NetworkInterface',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=120, verbose_name='Interface Name(eg. eth0)')),
                ('hostname', models.CharField(max_length=255)),
                ('domainname', models.CharField(max_length=255)),
                ('ipaddress', models.GenericIPAddressField(verbose_name='IP Address ')),
                ('mac', models.CharField(max_length=100, verbose_name='MAC Address')),
                ('switch_port', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='networks.switchport', verbose_name='Switch Port')),
                ('system', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='systems.system')),
            ],
        ),
    ]
