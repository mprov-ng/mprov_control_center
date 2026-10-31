import json
import os

from django.core import management
from django.core.management.base import BaseCommand, CommandError

from utils.backup_apps import MANIFEST_NAME


class Command(BaseCommand):
    help = (
        "Restore an mProv data backup created by mprov_backup. All fixture "
        "files are passed to a single manage.py loaddata call, so Django "
        "defers foreign-key constraint checking until every file has been "
        "loaded -- this avoids app load-order/dependency errors, including "
        "the systems<->disklayouts cycle. Intended for restoring onto a "
        "freshly migrated, empty database; restoring into a populated one "
        "can raise IntegrityErrors on colliding primary keys."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "backup_dir",
            help="Path to a backup directory created by mprov_backup (contains manifest.json).",
        )

    def handle(self, *args, **options):
        backup_dir = options["backup_dir"]
        manifest_path = os.path.join(backup_dir, MANIFEST_NAME)
        if not os.path.exists(manifest_path):
            raise CommandError(f"No {MANIFEST_NAME} found in {backup_dir}")

        with open(manifest_path) as fh:
            manifest = json.load(fh)

        fixture_paths = [os.path.join(backup_dir, name) for name in manifest["files"]]
        missing = [p for p in fixture_paths if not os.path.exists(p)]
        if missing:
            raise CommandError("Missing fixture file(s): " + ", ".join(missing))

        self.stdout.write(f"Loading {len(fixture_paths)} fixture file(s) from {backup_dir} ...")
        management.call_command("loaddata", *fixture_paths)
        self.stdout.write(self.style.SUCCESS("Restore complete."))
