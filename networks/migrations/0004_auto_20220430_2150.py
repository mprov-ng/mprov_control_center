# Generated by Django 3.2.12 on 2022-04-30 21:50

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('networks', '0003_alter_network_slug'),
    ]

    operations = [
        migrations.AddField(
            model_name='network',
            name='domain',
            field=models.CharField(default='test.cluster', max_length=255),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='network',
            name='isbootable',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='network',
            name='isdhcp',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='network',
            name='managedns',
            field=models.BooleanField(default=False),
        ),
        migrations.AlterField(
            model_name='network',
            name='slug',
            field=models.SlugField(unique=True, verbose_name='Network ID'),
        ),
    ]