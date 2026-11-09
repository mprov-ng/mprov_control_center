""" Django's side of the signing helper (pki.signer, #381): Django never
reads ca.key; it asks the root-run helper over its Unix socket. """
import json
import socket
import time

from django.conf import settings

from pki.ca import PKIError


class SignerUnavailable(PKIError):
    """ The signing helper couldn't be reached. """


# a connect() refused with EAGAIN because the helper's listen queue is full
# is tried again this many times, this far apart (#534): the queue drains in
# milliseconds.
CONNECT_TRIES = 3
CONNECT_RETRY_DELAY = 0.05


def _ask(path, request, timeout):
    """ One round trip to the helper: the raw reply line. """
    for attempt in range(CONNECT_TRIES):
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
            s.settimeout(timeout)
            try:
                s.connect(path)
            except BlockingIOError:
                if attempt == CONNECT_TRIES - 1:
                    raise
                time.sleep(CONNECT_RETRY_DELAY * (attempt + 1))
                continue
            s.sendall(request.encode() + b"\n")
            return s.makefile("rb").readline()


def socket_signer(kind, name, lifetime, csr_pem, path=None, timeout=10):
    """ The PEM certificate the helper signs, or PKIError with its reason. """
    path = path or settings.MPROV_SIGNER_SOCKET
    request = json.dumps({"kind": kind, "name": name, "lifetime": lifetime.total_seconds(),
                          "csr": csr_pem if isinstance(csr_pem, str) else csr_pem.decode()})
    try:
        reply = _ask(path, request, timeout)
    except OSError as e:
        raise SignerUnavailable(f"the signing helper isn't reachable at {path}: {e}")
    try:
        reply = json.loads(reply)
    except ValueError:
        raise SignerUnavailable("the signing helper sent no reply.")
    if "certificate" not in reply:
        raise PKIError(reply.get("error", "the signing helper refused."))
    return reply["certificate"]


def local_signer(ca):
    """ A signer that signs in this process with ca, applying the helper's
    policy: for tests and tools that already hold the CA. """
    from pki.signer import handle

    def sign(kind, name, lifetime, csr_pem):
        reply = handle(ca, {"kind": kind, "name": name, "lifetime": lifetime.total_seconds(),
                            "csr": csr_pem if isinstance(csr_pem, str) else csr_pem.decode()})
        if "certificate" not in reply:
            raise PKIError(reply["error"])
        return reply["certificate"]
    return sign
