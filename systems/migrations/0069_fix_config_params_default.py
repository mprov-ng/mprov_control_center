from django.db import migrations

OLD_DEFAULT = "# Inherit from System Group or Distribtion."
NEW_DEFAULT = "# Inherit from System Group or Distribution."

def fix_config_params_default(apps, schema_editor):
    # Only rows still holding the untouched old default.  update() skips the
    # save signals, so no image rebuilds are queued.
    for modelName in ('System', 'SystemImage'):
        model = apps.get_model('systems', modelName)
        model.objects.filter(config_params=OLD_DEFAULT).update(config_params=NEW_DEFAULT)

class Migration(migrations.Migration):

    dependencies = [
        ('systems', '0068_model_text_fixes'),
    ]

    operations = [
        migrations.RunPython(fix_config_params_default, migrations.RunPython.noop)
    ]
