""" The mPCC's own certificate authority (#381).

Each install makes its own CA at first start.  The CA signs the HTTPS
certificate the mPCC serves, and later the client certificates its job
servers and booted systems authenticate with.  Everything is EC P-256.

Files, in MPROV_TLS_DIR (default /var/lib/mprov/tls, a volume of its own):
- ca.key, ca.crt: the CA.  ca.key is root-only.
- server.key, server.crt: the HTTPS certificate, signed by the CA, renewed at
  start when it's under SERVER_RENEW_BEFORE from expiry or its names change.

A site that mounts its own HTTPS certificate (MPROV_TLS_CERT and
MPROV_TLS_KEY) has it served as is.  The CA is still made, as it's what
client certificates are checked against.
"""
import datetime
import ipaddress
import os
import tempfile
from dataclasses import dataclass

from cryptography import x509
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

CA_LIFETIME = datetime.timedelta(days=3650)
SERVER_LIFETIME = datetime.timedelta(days=365)
SERVER_RENEW_BEFORE = datetime.timedelta(days=30)
# not_before is set this far back, so a node whose clock is a little behind
# still accepts a certificate made a moment ago.
BACKDATE = datetime.timedelta(hours=1)
# a CSR is a few hundred bytes; anything much bigger isn't one.
MAX_CSR_BYTES = 16 * 1024
ORGANIZATION = "mProv"

CA_KEY = "ca.key"
CA_CERT = "ca.crt"
SERVER_KEY = "server.key"
SERVER_CERT = "server.crt"


class PKIError(Exception):
    """ A CA, certificate or CSR problem, with a message for the operator or client. """


def utcnow():
    return datetime.datetime.now(datetime.timezone.utc)


def new_key():
    return ec.generate_private_key(ec.SECP256R1())


def fingerprint(cert):
    """ The certificate's SHA-256 fingerprint, as lowercase hex. """
    return cert.fingerprint(hashes.SHA256()).hex()


def cert_pem(cert):
    return cert.public_bytes(serialization.Encoding.PEM).decode()


def _public_der(key):
    return key.public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)


def key_matches(cert, key):
    return _public_der(cert.public_key()) == _public_der(key.public_key())


def _write(path, data, mode):
    """ Write data to path atomically, created with mode, so a crash never
    leaves a half-written key, and a key is never readable by others even
    for a moment. """
    directory = os.path.dirname(path) or "."
    fd, tmp = tempfile.mkstemp(dir=directory, prefix=".tmp-")
    try:
        os.fchmod(fd, mode)
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def write_key(path, key):
    _write(path, key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                   serialization.NoEncryption()), 0o600)


def write_cert(path, cert):
    _write(path, cert.public_bytes(serialization.Encoding.PEM), 0o644)


def load_key(path):
    try:
        with open(path, "rb") as f:
            return serialization.load_pem_private_key(f.read(), password=None)
    except (OSError, ValueError, TypeError) as e:
        raise PKIError(f"can't read the private key {path}: {e}")


def load_cert(path):
    try:
        with open(path, "rb") as f:
            return x509.load_pem_x509_certificate(f.read())
    except (OSError, ValueError) as e:
        raise PKIError(f"can't read the certificate {path}: {e}")


def issued_by(cert, issuer):
    """ Whether issuer's key signed cert. """
    try:
        cert.verify_directly_issued_by(issuer)
        return True
    except (ValueError, TypeError, InvalidSignature):
        return False


@dataclass
class CA:
    key: object
    cert: object

    @classmethod
    def create(cls, common_name, now=None):
        now = now or utcnow()
        key = new_key()
        name = x509.Name([
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, ORGANIZATION),
            x509.NameAttribute(NameOID.COMMON_NAME, common_name),
        ])
        cert = (
            x509.CertificateBuilder()
            .subject_name(name)
            .issuer_name(name)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - BACKDATE)
            .not_valid_after(now + CA_LIFETIME)
            .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
            .add_extension(x509.KeyUsage(
                digital_signature=False, content_commitment=False, key_encipherment=False,
                data_encipherment=False, key_agreement=False, key_cert_sign=True, crl_sign=True,
                encipher_only=False, decipher_only=False), critical=True)
            .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()), critical=False)
            .sign(key, hashes.SHA256())
        )
        return cls(key, cert)

    @classmethod
    def load(cls, directory):
        """ The CA in directory, or None if there isn't one yet. """
        key_path = os.path.join(directory, CA_KEY)
        cert_path = os.path.join(directory, CA_CERT)
        have_key, have_cert = os.path.exists(key_path), os.path.exists(cert_path)
        if not have_key and not have_cert:
            return None
        if have_key != have_cert:
            missing = key_path if not have_key else cert_path
            # never make a new CA over half of an old one: every certificate it
            # signed would stop working.
            raise PKIError(f"{missing} is missing, but the rest of the CA is there. Restore it, "
                           f"or remove both {CA_KEY} and {CA_CERT} to make a new CA, which "
                           f"invalidates every certificate the old one signed.")
        ca = cls(load_key(key_path), load_cert(cert_path))
        if not key_matches(ca.cert, ca.key):
            raise PKIError(f"{key_path} doesn't match {cert_path}.")
        return ca

    def save(self, directory):
        write_key(os.path.join(directory, CA_KEY), self.key)
        write_cert(os.path.join(directory, CA_CERT), self.cert)

    def _builder(self, subject, public_key, lifetime, now):
        return (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(self.cert.subject)
            .public_key(public_key)
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - BACKDATE)
            .not_valid_after(min(now + lifetime, self.cert.not_valid_after_utc))
            .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
            .add_extension(x509.KeyUsage(
                digital_signature=True, content_commitment=False, key_encipherment=False,
                data_encipherment=False, key_agreement=False, key_cert_sign=False, crl_sign=False,
                encipher_only=False, decipher_only=False), critical=True)
            .add_extension(x509.SubjectKeyIdentifier.from_public_key(public_key), critical=False)
            .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(self.key.public_key()),
                           critical=False)
        )

    def issue_server_cert(self, dns_names, ip_addresses, now=None):
        """ A new key and HTTPS certificate for the mPCC, for these names. """
        now = now or utcnow()
        key = new_key()
        subject = x509.Name([
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, ORGANIZATION),
            x509.NameAttribute(NameOID.COMMON_NAME, (list(dns_names) or ["mprov-mpcc"])[0]),
        ])
        san = [x509.DNSName(n) for n in dns_names] + [x509.IPAddress(ipaddress.ip_address(i)) for i in ip_addresses]
        cert = (
            self._builder(subject, key.public_key(), SERVER_LIFETIME, now)
            .add_extension(x509.SubjectAlternativeName(san), critical=False)
            .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
            .sign(self.key, hashes.SHA256())
        )
        return key, cert

    def sign_csr(self, csr, common_name, kind, lifetime, now=None):
        """ A client certificate for an agent, from its checked CSR.  The
        subject comes from the mPCC, never from the CSR. """
        now = now or utcnow()
        subject = x509.Name([
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, ORGANIZATION),
            x509.NameAttribute(NameOID.ORGANIZATIONAL_UNIT_NAME, kind),
            x509.NameAttribute(NameOID.COMMON_NAME, common_name),
        ])
        return (
            self._builder(subject, csr.public_key(), lifetime, now)
            .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.CLIENT_AUTH]), critical=False)
            .sign(self.key, hashes.SHA256())
        )


def check_csr(pem):
    """ The CSR in pem, if it's well-formed, self-signed and uses an accepted
    key: EC P-256 or P-384, or RSA of at least 2048 bits. """
    if isinstance(pem, str):
        pem = pem.encode()
    if not pem or len(pem) > MAX_CSR_BYTES:
        raise PKIError("not a CSR.")
    try:
        csr = x509.load_pem_x509_csr(pem)
    except ValueError:
        raise PKIError("not a PEM CSR.")
    if not csr.is_signature_valid:
        raise PKIError("the CSR's signature is invalid.")
    key = csr.public_key()
    if isinstance(key, ec.EllipticCurvePublicKey):
        if not isinstance(key.curve, (ec.SECP256R1, ec.SECP384R1)):
            raise PKIError(f"EC keys must be P-256 or P-384, not {key.curve.name}.")
    elif isinstance(key, rsa.RSAPublicKey):
        if key.key_size < 2048:
            raise PKIError(f"RSA keys must be at least 2048 bits, not {key.key_size}.")
    else:
        raise PKIError("the key must be EC (P-256 or P-384) or RSA.")
    return csr


def server_cert_problem(ca, cert, key, dns_names, ip_addresses, now=None):
    """ Why the HTTPS certificate needs renewing, or None if it's fine. """
    now = now or utcnow()
    if not key_matches(cert, key):
        return "its key doesn't match"
    if not issued_by(cert, ca.cert):
        return "it isn't signed by this CA"
    if cert.not_valid_after_utc - now < SERVER_RENEW_BEFORE:
        return f"it expires {cert.not_valid_after_utc:%Y-%m-%d}"
    try:
        san = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
    except x509.ExtensionNotFound:
        return "it has no subject alternative names"
    have = set(san.get_values_for_type(x509.DNSName)) | {str(i) for i in san.get_values_for_type(x509.IPAddress)}
    missing = [n for n in list(dns_names) + list(ip_addresses) if n not in have]
    if missing:
        return f"it doesn't cover {', '.join(missing)}"
    return None


def parse_ips(values):
    ips = []
    for value in values:
        try:
            ips.append(str(ipaddress.ip_address(value)))
        except ValueError:
            raise PKIError(f"{value!r} is not an IP address.")
    return ips


def ensure_tls(directory, dns_names, ip_addresses, site_cert=None, site_key=None, ca_name="mProv CA",
               now=None, log=print):
    """ Make sure directory has a CA and, unless the site supplies its own, a
    current HTTPS certificate for these names.  Returns the paths Apache
    serves: {"cert", "key", "ca"}. """
    now = now or utcnow()
    ip_addresses = parse_ips(ip_addresses)
    os.makedirs(directory, mode=0o755, exist_ok=True)
    ca = CA.load(directory)
    if ca is None:
        ca = CA.create(ca_name, now)
        ca.save(directory)
        log(f"Made a new CA, fingerprint {fingerprint(ca.cert)}")
    elif ca.cert.not_valid_after_utc <= now:
        raise PKIError(f"the CA in {directory} expired {ca.cert.not_valid_after_utc:%Y-%m-%d}.")
    paths = {"ca": os.path.join(directory, CA_CERT)}

    if site_cert or site_key:
        if not (site_cert and site_key):
            raise PKIError("set both MPROV_TLS_CERT and MPROV_TLS_KEY, or neither.")
        cert, key = load_cert(site_cert), load_key(site_key)
        if not key_matches(cert, key):
            raise PKIError(f"{site_key} doesn't match {site_cert}.")
        log(f"Serving the site's own HTTPS certificate {site_cert}")
        paths.update(cert=site_cert, key=site_key)
        return paths

    cert_path, key_path = os.path.join(directory, SERVER_CERT), os.path.join(directory, SERVER_KEY)
    problem = "there isn't one"
    if os.path.exists(cert_path) and os.path.exists(key_path):
        try:
            problem = server_cert_problem(ca, load_cert(cert_path), load_key(key_path), dns_names, ip_addresses, now)
        except PKIError as e:
            problem = str(e)
    if problem:
        key, cert = ca.issue_server_cert(dns_names, ip_addresses, now)
        write_key(key_path, key)
        write_cert(cert_path, cert)
        log(f"Made a new HTTPS certificate ({problem}) for {', '.join(list(dns_names) + ip_addresses)}, "
            f"valid to {cert.not_valid_after_utc:%Y-%m-%d}")
    paths.update(cert=cert_path, key=key_path)
    return paths
