import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('authcustom', '0001_user_tokens'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='usertoken',
            name='created_by',
            field=models.ForeignKey(blank=True, editable=False, null=True,
                                    on_delete=django.db.models.deletion.SET_NULL, related_name='+',
                                    to=settings.AUTH_USER_MODEL, verbose_name='Made By'),
        ),
    ]
