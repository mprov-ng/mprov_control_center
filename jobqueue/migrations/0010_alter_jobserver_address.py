# Generated by Django 3.2.23 on 2024-01-02 18:46

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('jobqueue', '0009_alter_jobserver_port'),
    ]

    operations = [
        migrations.AlterField(
            model_name='jobserver',
            name='address',
            field=models.CharField(default='mprov', max_length=1024),
        ),
    ]
