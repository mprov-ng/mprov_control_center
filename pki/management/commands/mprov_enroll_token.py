""" Make a job server enrollment token (#381).

    manage.py mprov_enroll_token [--hours 24] [--note ...]
        prints a new token (and the CA fingerprint to check).

    manage.py mprov_enroll_token --bootstrap /etc/mprov/enroll_token
        what init_mpcc.sh runs at every start: writes a new token there
        (0600) for the job server in the same compose stack, only while no
        job server has an active credential and the file has no usable token.
"""
import datetime
import os

from django.core.management.base import BaseCommand

from pki.admin import ca_fingerprint
from pki.models import AgentCredential, EnrollmentToken, _hash


class Command(BaseCommand):
    help = "Make a one-time job server enrollment token."

    def add_arguments(self, parser):
        parser.add_argument("--hours", type=int, default=24)
        parser.add_argument("--note", default="")
        parser.add_argument("--bootstrap", metavar="FILE",
                            help="write a token to FILE for the local job server, if it still needs one")

    def handle(self, *args, **options):
        lifetime = datetime.timedelta(hours=options["hours"])
        path = options["bootstrap"]
        if path:
            if AgentCredential.objects.active().filter(kind=AgentCredential.JOBSERVER).exists():
                return
            if self.usable_in(path):
                return
            _, secret = EnrollmentToken.make(lifetime, note=options["note"] or "local job server (init_mpcc.sh)")
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w") as f:
                f.write(secret + "\n")
            os.chmod(path, 0o600)
            self.stderr.write(f"Wrote a job server enrollment token to {path}, valid {options['hours']}h.")
            return
        _, secret = EnrollmentToken.make(lifetime, note=options["note"])
        self.stdout.write(f"token: {secret}\nCA fingerprint: {ca_fingerprint()}")

    @staticmethod
    def usable_in(path):
        try:
            with open(path) as f:
                secret = f.read().strip()
        except OSError:
            return False
        row = EnrollmentToken.objects.filter(token_hash=_hash(secret)).first() if secret else None
        return row is not None and row.usable()
