# Generated by Django 3.2.18 on 2023-04-03 14:21

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('scripts', '0007_auto_20230321_1939'),
    ]

    operations = [
        migrations.AddField(
            model_name='ansiblerole',
            name='roleurl',
            field=models.CharField(default='http://localhost', max_length=2048, verbose_name='Role URL'),
            preserve_default=False,
        ),
    ]