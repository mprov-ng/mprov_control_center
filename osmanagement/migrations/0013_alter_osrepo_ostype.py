# Generated by Django 3.2.13 on 2022-07-25 15:46

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('osmanagement', '0012_auto_20220719_1840'),
    ]

    operations = [
        migrations.AlterField(
            model_name='osrepo',
            name='ostype',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='osmanagement.ostype', verbose_name='OS Type'),
        ),
    ]
