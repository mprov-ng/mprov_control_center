import json
import os
from datetime import datetime

from django.conf import settings
from django.core import management
from django.core.management.base import BaseCommand

from utils.backup_apps import BACKUP_LABELS, MANIFEST_NAME


class Command(BaseCommand):
    help = (
        "Back up mProv data with manage.py dumpdata: one fixture file per app, "
        "in the order mprov_restore needs to load them, plus a manifest."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--output-dir",
            default=os.path.join(settings.BASE_DIR, "backups"),
            help="Directory to create the timestamped backup subdirectory in (default: backups/).",
        )
        parser.add_argument(
            "--indent",
            type=int,
            default=2,
            help="JSON indent for the fixture files (default: 2).",
        )

    def handle(self, *args, **options):
        indent = options["indent"]
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup_dir = os.path.join(options["output_dir"], f"mprov-backup-{timestamp}")
        os.makedirs(backup_dir)

        manifest = {"created": timestamp, "labels": BACKUP_LABELS, "files": []}

        for index, label in enumerate(BACKUP_LABELS):
            filename = f"{index:02d}-{label}.json"
            path = os.path.join(backup_dir, filename)
            self.stdout.write(f"Dumping {label} -> {filename}")
            with open(path, "w") as fh:
                management.call_command(
                    "dumpdata",
                    label,
                    indent=indent,
                    stdout=fh,
                )
            manifest["files"].append(filename)

        with open(os.path.join(backup_dir, MANIFEST_NAME), "w") as fh:
            json.dump(manifest, fh, indent=2)

        self.stdout.write(self.style.SUCCESS(f"Backup complete: {backup_dir}"))
