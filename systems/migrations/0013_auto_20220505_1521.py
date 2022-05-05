# Generated by Django 3.2.13 on 2022-05-05 15:21

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('systems', '0012_systembmc'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='systembmc',
            options={'verbose_name': 'Power Management', 'verbose_name_plural': 'Power Management'},
        ),
        migrations.AlterField(
            model_name='networkinterface',
            name='name',
            field=models.CharField(max_length=50, verbose_name='Interface Name(eg. eth0)'),
        ),
    ]