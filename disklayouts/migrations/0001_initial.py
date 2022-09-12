# Generated by Django 3.2.13 on 2022-08-04 13:46

from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='DiskLayout',
            fields=[
                ('name', models.CharField(max_length=255, verbose_name='Layout Name')),
                ('diskname', models.CharField(max_length=255, verbose_name='Disk Device')),
                ('slug', models.SlugField(primary_key=True, serialize=False)),
            ],
        ),
        migrations.CreateModel(
            name='DiskPartition',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('mount', models.CharField(max_length=4096, verbose_name='Mount Point')),
                ('size', models.BigIntegerField(verbose_name='Size')),
                ('fill', models.BooleanField(default=False, verbose_name='Grow to fill?')),
                ('filesystem', models.CharField(max_length=255, verbose_name='Filesysetm')),
            ],
        ),
    ]