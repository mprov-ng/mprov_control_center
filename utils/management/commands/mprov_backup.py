import json
import os
from datetime import datetime

from django.conf import settings
from django.core import management
from django.core.management.base import BaseCommand, CommandError

from utils.backup_apps import BACKUP_LABELS, MANIFEST_NAME


class Command(BaseCommand):
    help = (
        "Back up mProv data with manage.py dumpdata: one fixture file per app, "
        "in the order mprov_restore needs to load them, plus a manifest."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--output-dir",
            default=settings.MPROV_BACKUP_DIR,
            help=f"Directory to create the timestamped backup subdirectory in (default: {settings.MPROV_BACKUP_DIR}).",
        )
        parser.add_argument(
            "--indent",
            type=int,
            default=2,
            help="JSON indent for the fixture files (default: 2).",
        )

    def handle(self, *args, **options):
        indent = options["indent"]
        # Apache serves media/ and static/, and a backup holds password
        # hashes, API keys and BMC passwords (#457).  realpath, because db/
        # is a link to media/.
        output_dir = os.path.realpath(options["output_dir"])
        for served in (settings.MEDIA_ROOT, settings.STATIC_ROOT):
            served = os.path.realpath(served)
            if os.path.commonpath([output_dir, served]) == served:
                raise CommandError(f"Not writing a backup under {served}: the web server serves it. Use another --output-dir.")
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup_dir = os.path.join(output_dir, f"mprov-backup-{timestamp}")
        # readable by the owner only, whatever the umask.
        umask = os.umask(0o077)
        try:
            self.write_backup(backup_dir, timestamp, indent)
        finally:
            os.umask(umask)

    def write_backup(self, backup_dir, timestamp, indent):
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
