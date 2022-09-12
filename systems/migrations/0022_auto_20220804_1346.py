# Generated by Django 3.2.13 on 2022-08-04 13:46

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('disklayouts', '0001_initial'),
        ('systems', '0021_auto_20220801_1521'),
    ]

    operations = [
        migrations.AddField(
            model_name='system',
            name='bootdisk',
            field=models.ForeignKey(blank=True, help_text='Boot disk for stateful installs', null=True, on_delete=django.db.models.deletion.SET_NULL, to='disklayouts.disklayout', verbose_name='Boot Disk'),
        ),
        migrations.AddField(
            model_name='system',
            name='stateful',
            field=models.BooleanField(default=False, help_text='Should this system use images to disk?', verbose_name='Stateful System?'),
        ),
    ]