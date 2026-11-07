""" Make sure the mPCC has its CA and a current HTTPS certificate (#381).

init_mpcc.sh runs this as root at every start, before Apache:

    eval "$(python manage.py mprov_tls --shell)"

which exports MPROV_TLS_CERT, MPROV_TLS_KEY and MPROV_TLS_CA for Apache's
ssl.conf.  The certificate covers MPROV_MPCC_HOSTNAME (and its
MPROV_DOMAINNAME name), the MPROV_MPCC_IPs addresses, localhost and
127.0.0.1.  A site's own certificate in MPROV_TLS_CERT/MPROV_TLS_KEY is
served as is.
"""
import os
import shlex
import socket
import sys

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from pki.ca import PKIError, ensure_tls


def names_from_env(environ):
    host = environ.get("MPROV_MPCC_HOSTNAME", "").strip()
    domain = environ.get("MPROV_DOMAINNAME", "").strip()
    dns = []
    for name in (host, f"{host}.{domain}" if host and domain else "", "localhost"):
        if name and name not in dns:
            dns.append(name)
    if not host:
        fqdn = socket.getfqdn()
        if fqdn and fqdn not in dns:
            dns.insert(0, fqdn)
    ips = [i.strip() for i in environ.get("MPROV_MPCC_IPs", "").split(",") if i.strip()]
    if "127.0.0.1" not in ips:
        ips.append("127.0.0.1")
    return dns, ips


class Command(BaseCommand):
    help = "Make the mPCC's CA and HTTPS certificate if they're missing, and renew the certificate when needed."

    def add_arguments(self, parser):
        parser.add_argument("--dir", default=settings.MPROV_TLS_DIR,
                            help="where the CA and certificate live (default: %(default)s)")
        parser.add_argument("--shell", action="store_true",
                            help="print export lines for MPROV_TLS_CERT, MPROV_TLS_KEY and MPROV_TLS_CA")

    def handle(self, *args, **options):
        dns, ips = names_from_env(os.environ)
        host = dns[0] if dns else "mprov-mpcc"
        try:
            paths = ensure_tls(
                options["dir"], dns, ips,
                site_cert=os.environ.get("MPROV_TLS_CERT", "").strip() or None,
                site_key=os.environ.get("MPROV_TLS_KEY", "").strip() or None,
                ca_name=f"mProv CA ({host})",
                # status goes to stderr, so --shell's stdout is only the exports.
                log=lambda line: print(line, file=sys.stderr),
            )
        except PKIError as e:
            raise CommandError(f"TLS setup failed: {e}")
        if options["shell"]:
            for var, key in (("MPROV_TLS_CERT", "cert"), ("MPROV_TLS_KEY", "key"), ("MPROV_TLS_CA", "ca")):
                self.stdout.write(f"export {var}={shlex.quote(paths[key])}")
        else:
            for key in ("cert", "key", "ca"):
                self.stdout.write(f"{key}: {paths[key]}")
