# Generated by Django 3.2.13 on 2022-09-02 02:19

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('disklayouts', '0021_raidlayout_raidlevel'),
    ]

    operations = [
        migrations.AddField(
            model_name='raidlayout',
            name='mount',
            field=models.CharField(default='/home', max_length=4096, verbose_name='Mount Point'),
            preserve_default=False,
        ),
    ]
