""" Client-certificate authentication for agents (#381).

Apache asks every HTTPS client for an optional certificate from the mPCC's
CA (static/configs/mprov_ssl_client.conf), verifies it, and passes it on as
SSL_CLIENT_VERIFY and SSL_CLIENT_CERT.  This maps a verified certificate to
the AgentCredential the mPCC issued for it: request.user becomes the agent's
service user, and request.auth the credential, which the permission rules
(pki.rules) then check.

A request is accepted only if all of these hold:
- Apache verified the certificate (SSL_CLIENT_VERIFY == SUCCESS), or a proxy
  in TRUSTED_PROXIES forwarded it in X-SSL-Client-Cert;
- it was issued by this install's CA (checked again here);
- its fingerprint matches a credential that isn't revoked and is in date;
- for a system's credential, the request comes from one of that system's
  network interface addresses (defence in depth; the certificate is the
  identity).
Anything else with a certificate is refused outright, never treated as
anonymous.  A request with no certificate is left to the other
authenticators.
"""
import datetime
import functools
import logging
import os
from ipaddress import ip_address, ip_network
from urllib.parse import unquote

from cryptography import x509
from django.conf import settings
from django.utils import timezone
from rest_framework import authentication, exceptions

from pki.ca import CA_CERT, fingerprint, issued_by

log = logging.getLogger("mprov.auth")

PROXY_HEADER = "HTTP_X_SSL_CLIENT_CERT"
# last_seen is written at most this often per credential.
LAST_SEEN_EVERY = datetime.timedelta(minutes=5)


@functools.lru_cache(maxsize=4)
def _ca_cert(path, mtime):
    with open(path, "rb") as f:
        return x509.load_pem_x509_certificate(f.read())


def ca_cert():
    """ This install's CA certificate, or None if there isn't one. """
    path = os.path.join(settings.MPROV_TLS_DIR, CA_CERT)
    try:
        return _ca_cert(path, os.stat(path).st_mtime_ns)
    except (OSError, ValueError):
        return None


def from_trusted_proxy(request):
    trusted = getattr(settings, "TRUSTED_PROXIES", [])
    try:
        peer = ip_address(request.META.get("REMOTE_ADDR", ""))
        return any(peer in ip_network(entry) for entry in trusted)
    except ValueError:
        return False


def presented_certificate(request):
    """ The PEM client certificate this request was made with, or None. """
    meta = request.META
    pem = meta.get("SSL_CLIENT_CERT")
    if pem:
        if meta.get("SSL_CLIENT_VERIFY") != "SUCCESS":
            raise exceptions.AuthenticationFailed("The client certificate wasn't verified.")
        return pem
    if meta.get(PROXY_HEADER) and from_trusted_proxy(request):
        # nginx and others URL-encode the PEM into the header.
        return unquote(meta[PROXY_HEADER])
    return None


class ClientCertAuthentication(authentication.BaseAuthentication):
    def authenticate(self, request):
        pem = presented_certificate(request)
        if pem is None:
            return None
        from pki.models import AgentCredential
        try:
            cert = x509.load_pem_x509_certificate(pem.encode() if isinstance(pem, str) else pem)
        except ValueError:
            raise exceptions.AuthenticationFailed("The client certificate couldn't be read.")
        ca = ca_cert()
        if ca is None or not issued_by(cert, ca):
            raise exceptions.AuthenticationFailed("The client certificate isn't from this mPCC's CA.")
        credential = (AgentCredential.objects.select_related("user", "system", "jobserver")
                      .filter(fingerprint=fingerprint(cert)).first())
        now = timezone.now()
        if credential is None or not credential.is_active(now):
            why = "unknown" if credential is None else "revoked or expired"
            log.warning(f"refused a client certificate ({why}), serial {cert.serial_number:x}, "
                        f"from {request.META.get('REMOTE_ADDR')}")
            raise exceptions.AuthenticationFailed("The client certificate is unknown, revoked or expired.")
        if credential.kind == AgentCredential.SYSTEM and not self.from_its_system(request, credential):
            log.warning(f"refused {credential.user.username}'s certificate from {request.META.get('REMOTE_ADDR')}, "
                        "which isn't one of its system's addresses")
            raise exceptions.AuthenticationFailed("This system's certificate is used from another address.")
        if not credential.user.is_active:
            raise exceptions.AuthenticationFailed("The agent's service user is disabled.")
        if credential.last_seen is None or now - credential.last_seen > LAST_SEEN_EVERY:
            AgentCredential.objects.filter(pk=credential.pk).update(last_seen=now)
        return (credential.user, credential)

    @staticmethod
    def from_its_system(request, credential):
        from systems.views_noauth import get_client_ip
        return credential.system.networkinterface_set.filter(ipaddress=get_client_ip(request)).exists()

    def authenticate_header(self, request):
        # 401, not 403, for a refused certificate.
        return 'TLS-Client-Certificate realm="mprov"'
