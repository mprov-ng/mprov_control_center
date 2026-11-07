""" The mPCC's signing helper (#381): the only process that reads ca.key.

init_mpcc.sh starts it as root before Apache:

    python -m pki.signer --dir /var/lib/mprov/tls --socket /run/mprov/signer.sock --group apache

It listens on a Unix socket that only root and the web server's group can
connect to.  Django (running as apache) sends it one JSON request per
connection, {"kind", "name", "lifetime", "csr"}, and gets back
{"certificate": PEM} or {"error": reason}.  It signs only what POLICY allows:
the agent kinds, a service-user name of the right shape for the kind, and at
most that kind's lifetime.  Every signature is logged.

No Django here: the helper loads nothing but pki.ca and cryptography.
"""
import argparse
import datetime
import grp
import json
import logging
import os
import re
import socketserver
import sys

from pki.ca import CA, PKIError, cert_pem, check_csr, fingerprint

log = logging.getLogger("mprov.signer")

# the most each kind may be issued (design: job server 90 days, system until
# its next boot plus a margin, image-build credential 2 hours).
POLICY = {
    "jobserver": (datetime.timedelta(days=90), re.compile(r"^mprov\.js\.[A-Za-z0-9._:-]{1,140}$")),
    "system": (datetime.timedelta(days=30), re.compile(r"^mprov\.sys\.[0-9]{1,18}$")),
    "build": (datetime.timedelta(hours=2), re.compile(r"^mprov\.build\.[A-Za-z0-9._-]{1,140}$")),
}
MAX_REQUEST = 64 * 1024


def handle(ca, request):
    """ Sign one request against POLICY.  Returns the reply dict. """
    if not isinstance(request, dict):
        return {"error": "not a request"}
    kind, name, lifetime, csr = (request.get(k) for k in ("kind", "name", "lifetime", "csr"))
    if kind not in POLICY:
        return {"error": f"unknown kind {kind!r}"}
    longest, shape = POLICY[kind]
    if not isinstance(name, str) or not shape.match(name):
        return {"error": f"bad name for a {kind} credential"}
    if not isinstance(lifetime, (int, float)) or isinstance(lifetime, bool) or lifetime <= 0:
        return {"error": "lifetime must be a positive number of seconds"}
    lifetime = min(datetime.timedelta(seconds=lifetime), longest)
    try:
        cert = ca.sign_csr(check_csr(csr if isinstance(csr, str) else ""), name, kind, lifetime)
    except PKIError as e:
        return {"error": str(e)}
    log.info(f"signed {kind} {name}: serial {cert.serial_number:x}, fingerprint {fingerprint(cert)}, "
             f"valid to {cert.not_valid_after_utc:%Y-%m-%dT%H:%M:%SZ}")
    return {"certificate": cert_pem(cert)}


class Handler(socketserver.StreamRequestHandler):
    def handle(self):
        line = self.rfile.readline(MAX_REQUEST + 1)
        if len(line) > MAX_REQUEST:
            reply = {"error": "request too large"}
        else:
            try:
                reply = handle(self.server.ca, json.loads(line))
            except ValueError:
                reply = {"error": "not JSON"}
            except Exception as e:  # never die on one bad request
                log.exception("signing failed")
                reply = {"error": f"signing failed: {e.__class__.__name__}"}
        self.wfile.write(json.dumps(reply).encode() + b"\n")


class Server(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
    daemon_threads = True


def serve(directory, path, group):
    ca = CA.load(directory)
    if ca is None:
        raise SystemExit(f"mprov signer: no CA in {directory}; run manage.py mprov_tls first.")
    if os.path.exists(path):
        os.unlink(path)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    old = os.umask(0o117)
    try:
        server = Server(path, Handler)
    finally:
        os.umask(old)
    gid = grp.getgrnam(group).gr_gid if group else -1
    os.chown(path, 0 if os.geteuid() == 0 else -1, gid)
    os.chmod(path, 0o660)
    server.ca = ca
    log.info(f"listening on {path} for group {group or '(own)'}, CA fingerprint {fingerprint(ca.cert)}")
    server.serve_forever()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dir", required=True)
    parser.add_argument("--socket", required=True)
    parser.add_argument("--group", default="")
    args = parser.parse_args(argv)
    logging.basicConfig(stream=sys.stderr, level=logging.INFO, format="[%(levelname).1s] mprov signer: %(message)s")
    serve(args.dir, args.socket, args.group)


if __name__ == "__main__":
    main()
