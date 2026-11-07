# When a BMC's stored credentials last changed (#374).

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('systems', '0074_system_serial_history'),
    ]

    operations = [
        migrations.AddField(
            model_name='systembmc',
            name='credentials_changed',
            field=models.DateTimeField(blank=True, editable=False, help_text='When the BMC username or password stored here last changed (#374).', null=True, verbose_name='Credentials Changed'),
        ),
    ]
