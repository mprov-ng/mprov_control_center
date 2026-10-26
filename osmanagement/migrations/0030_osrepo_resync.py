from django.db import migrations, models


def clear_resync(apps, schema_editor):
    # update used to stay set until a job server's PATCH cleared it, or for
    # ever on a repo that isn't mirrored.  resync is one-shot, so a leftover
    # value would re-sync the repo on its next save.
    apps.get_model('osmanagement', 'OSRepo').objects.update(resync=False)


class Migration(migrations.Migration):

    dependencies = [
        ('osmanagement', '0029_repo_option_labels'),
    ]

    operations = [
        migrations.RenameField(
            model_name='osrepo',
            old_name='update',
            new_name='resync',
        ),
        migrations.AlterField(
            model_name='osrepo',
            name='resync',
            field=models.BooleanField(default=False, help_text="On a mirrored repository, saving with this checked bumps the local version and queues a repo-update job to download it again, then clears this box. No effect on a repository that isn't mirrored.", verbose_name='Re-sync on save'),
        ),
        migrations.RunPython(clear_resync, migrations.RunPython.noop),
    ]
