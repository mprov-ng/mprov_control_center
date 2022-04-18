# Generated by Django 3.2.12 on 2022-04-01 19:52

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('networks', '0007_auto_20220401_1940'),
    ]

    operations = [
        migrations.AddField(
            model_name='switchport',
            name='networks',
            field=models.ManyToManyField(to='networks.NetworkType', verbose_name='Networks'),
        ),
        migrations.AlterField(
            model_name='network',
            name='netmask',
            field=models.IntegerField(choices=[(1, 1), (2, 2), (3, 3), (4, 4), (5, 5), (6, 6), (7, 7), (8, 8), (9, 9), (10, 10), (11, 11), (12, 12), (13, 13), (14, 14), (15, 15), (16, 16), (17, 17), (18, 18), (19, 19), (20, 20), (21, 21), (22, 22), (23, 23), (24, 24), (25, 25), (26, 26), (27, 27), (28, 28), (29, 29), (30, 30), (31, 31)], verbose_name='CIDR Mask'),
        ),
        migrations.AlterField(
            model_name='switch',
            name='network',
            field=models.ForeignKey(on_delete=django.db.models.deletion.DO_NOTHING, to='networks.network', verbose_name='Management\nNetwork'),
        ),
    ]
