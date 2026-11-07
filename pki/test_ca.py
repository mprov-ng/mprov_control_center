import base64
import datetime
import os
import shutil
import stat
import tempfile

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID
from django.test import SimpleTestCase

from pki import ca as pki
from pki.ca import CA, PKIError, check_csr, ensure_tls, issued_by, load_cert, load_key

DNS = ["mprov-mpcc", "mprov-mpcc.example.com", "localhost"]
IPS = ["10.1.2.1", "127.0.0.1"]


def make_csr(key=None, cn="whatever"):
    key = key or ec.generate_private_key(ec.SECP256R1())
    csr = (x509.CertificateSigningRequestBuilder()
           .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)]))
           .sign(key, hashes.SHA256()))
    return csr.public_bytes(serialization.Encoding.PEM)


def sans(cert):
    san = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
    return set(san.get_values_for_type(x509.DNSName)) | {str(i) for i in san.get_values_for_type(x509.IPAddress)}


class TLSDirTestCase(SimpleTestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir)
        self.log = []

    def path(self, name):
        return os.path.join(self.dir, name)

    def ensure(self, dns=DNS, ips=IPS, **kwargs):
        return ensure_tls(self.dir, dns, ips, log=self.log.append, **kwargs)

    def mode(self, name):
        return stat.S_IMODE(os.stat(self.path(name)).st_mode)


class EnsureTLSTests(TLSDirTestCase):
    """ #381: each install makes its own CA and an HTTPS certificate signed by it. """

    def test_first_start_makes_a_ca_and_a_server_cert(self):
        paths = self.ensure()
        self.assertEqual(paths, {"ca": self.path("ca.crt"), "cert": self.path("server.crt"), "key": self.path("server.key")})
        ca = CA.load(self.dir)
        server = load_cert(self.path("server.crt"))
        self.assertTrue(issued_by(server, ca.cert))
        self.assertEqual(sans(server), set(DNS + IPS))
        self.assertIn(ExtendedKeyUsageOID.SERVER_AUTH,
                      server.extensions.get_extension_for_class(x509.ExtendedKeyUsage).value)
        self.assertTrue(ca.cert.extensions.get_extension_for_class(x509.BasicConstraints).value.ca)
        self.assertEqual(len(self.log), 2)

    def test_keys_are_private(self):
        self.ensure()
        self.assertEqual(self.mode("ca.key"), 0o600)
        self.assertEqual(self.mode("server.key"), 0o600)
        self.assertEqual(self.mode("ca.crt"), 0o644)
        self.assertEqual(self.mode("server.crt"), 0o644)
        self.assertEqual([f for f in os.listdir(self.dir) if f.startswith(".tmp")], [])

    def test_each_install_gets_its_own_ca(self):
        other = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, other)
        self.ensure()
        ensure_tls(other, DNS, IPS, log=lambda line: None)
        self.assertNotEqual(pki.fingerprint(CA.load(self.dir).cert), pki.fingerprint(CA.load(other).cert))

    def test_a_restart_keeps_both(self):
        self.ensure()
        before = [open(self.path(f), "rb").read() for f in ("ca.key", "ca.crt", "server.key", "server.crt")]
        self.log.clear()
        self.ensure()
        after = [open(self.path(f), "rb").read() for f in ("ca.key", "ca.crt", "server.key", "server.crt")]
        self.assertEqual(before, after)
        self.assertEqual(self.log, [])

    def test_renewed_near_expiry(self):
        self.ensure()
        old = load_cert(self.path("server.crt"))
        later = old.not_valid_after_utc - pki.SERVER_RENEW_BEFORE + datetime.timedelta(days=1)
        self.ensure(now=later)
        new = load_cert(self.path("server.crt"))
        self.assertNotEqual(old.serial_number, new.serial_number)
        self.assertGreater(new.not_valid_after_utc, old.not_valid_after_utc)
        self.assertIn("expires", self.log[-1])

    def test_kept_until_near_expiry(self):
        self.ensure()
        old = load_cert(self.path("server.crt"))
        self.ensure(now=old.not_valid_after_utc - pki.SERVER_RENEW_BEFORE - datetime.timedelta(days=1))
        self.assertEqual(load_cert(self.path("server.crt")).serial_number, old.serial_number)

    def test_renewed_for_a_new_name_or_address(self):
        self.ensure()
        self.ensure(ips=IPS + ["10.1.2.2"])
        self.assertIn("10.1.2.2", sans(load_cert(self.path("server.crt"))))
        self.assertIn("doesn't cover 10.1.2.2", self.log[-1])
        self.ensure(dns=DNS + ["mpcc2"], ips=IPS + ["10.1.2.2"])
        self.assertIn("mpcc2", sans(load_cert(self.path("server.crt"))))

    def test_renewed_when_its_key_is_lost_or_broken(self):
        self.ensure()
        os.unlink(self.path("server.key"))
        self.ensure()
        self.assertTrue(pki.key_matches(load_cert(self.path("server.crt")), load_key(self.path("server.key"))))
        with open(self.path("server.key"), "w") as f:
            f.write("junk")
        self.ensure()
        self.assertTrue(pki.key_matches(load_cert(self.path("server.crt")), load_key(self.path("server.key"))))

    def test_renewed_when_signed_by_another_ca(self):
        self.ensure()
        other = CA.create("other")
        key, cert = other.issue_server_cert(DNS, IPS)
        pki.write_key(self.path("server.key"), key)
        pki.write_cert(self.path("server.crt"), cert)
        self.ensure()
        self.assertTrue(issued_by(load_cert(self.path("server.crt")), CA.load(self.dir).cert))

    def test_half_a_ca_is_an_error_not_a_new_ca(self):
        self.ensure()
        for missing in ("ca.key", "ca.crt"):
            with self.subTest(missing=missing):
                kept = open(self.path(missing), "rb").read()
                os.unlink(self.path(missing))
                with self.assertRaisesRegex(PKIError, "missing"):
                    self.ensure()
                with open(self.path(missing), "wb") as f:
                    f.write(kept)

    def test_mismatched_ca_key_is_an_error(self):
        self.ensure()
        pki.write_key(self.path("ca.key"), pki.new_key())
        with self.assertRaisesRegex(PKIError, "doesn't match"):
            self.ensure()

    def test_an_expired_ca_is_an_error(self):
        self.ensure()
        with self.assertRaisesRegex(PKIError, "expired"):
            self.ensure(now=CA.load(self.dir).cert.not_valid_after_utc + datetime.timedelta(days=1))

    def test_a_bad_ip_is_an_error(self):
        with self.assertRaisesRegex(PKIError, "not an IP"):
            self.ensure(ips=["10.1.2"])


class SiteCertificateTests(TLSDirTestCase):
    """ #381: a site's own HTTPS certificate is served as is; the CA is still made. """

    def setUp(self):
        super().setUp()
        site = CA.create("Site CA")
        self.key, self.cert = site.issue_server_cert(["mpcc.site.example"], [])
        self.site_cert, self.site_key = self.path("site.crt"), self.path("site.key")
        pki.write_cert(self.site_cert, self.cert)
        pki.write_key(self.site_key, self.key)

    def test_served_as_is(self):
        paths = self.ensure(site_cert=self.site_cert, site_key=self.site_key)
        self.assertEqual(paths, {"ca": self.path("ca.crt"), "cert": self.site_cert, "key": self.site_key})
        self.assertFalse(os.path.exists(self.path("server.crt")))
        self.assertIsNotNone(CA.load(self.dir))

    def test_both_or_neither(self):
        with self.assertRaisesRegex(PKIError, "both"):
            self.ensure(site_cert=self.site_cert)

    def test_key_must_match(self):
        pki.write_key(self.site_key, pki.new_key())
        with self.assertRaisesRegex(PKIError, "doesn't match"):
            self.ensure(site_cert=self.site_cert, site_key=self.site_key)

    def test_unreadable(self):
        with self.assertRaisesRegex(PKIError, "can't read"):
            self.ensure(site_cert=self.path("nope.crt"), site_key=self.site_key)


class CSRTests(SimpleTestCase):
    """ #381: agents send a CSR; only well-formed ones with a strong key are signed. """

    def setUp(self):
        self.ca = CA.create("test CA")

    def test_ec_p256_and_p384_and_rsa_2048(self):
        for key in (ec.generate_private_key(ec.SECP256R1()), ec.generate_private_key(ec.SECP384R1()),
                    rsa.generate_private_key(public_exponent=65537, key_size=2048)):
            with self.subTest(key=type(key).__name__):
                check_csr(make_csr(key))

    def test_weak_keys_refused(self):
        for key in (ec.generate_private_key(ec.SECP192R1()),
                    rsa.generate_private_key(public_exponent=65537, key_size=1024)):
            with self.subTest(key=type(key).__name__):
                with self.assertRaises(PKIError):
                    check_csr(make_csr(key))

    def test_garbage_refused(self):
        for pem in (b"", b"hello", b"-----BEGIN CERTIFICATE REQUEST-----\nAAAA\n-----END CERTIFICATE REQUEST-----\n",
                    b"x" * (pki.MAX_CSR_BYTES + 1)):
            with self.subTest(pem=pem[:20]):
                with self.assertRaises(PKIError):
                    check_csr(pem)

    def test_a_tampered_csr_is_refused(self):
        # flip a bit in the signature at the end of the DER
        der = bytearray(x509.load_pem_x509_csr(make_csr()).public_bytes(serialization.Encoding.DER))
        der[-3] ^= 0x01
        pem = (b"-----BEGIN CERTIFICATE REQUEST-----\n" + base64.encodebytes(bytes(der))
               + b"-----END CERTIFICATE REQUEST-----\n")
        with self.assertRaises(PKIError):
            check_csr(pem)

    def test_signed_client_cert(self):
        key = ec.generate_private_key(ec.SECP256R1())
        now = pki.utcnow()
        cert = self.ca.sign_csr(check_csr(make_csr(key, cn="admin")), "mprov.sys.7", "system",
                                datetime.timedelta(days=30), now)
        self.assertTrue(issued_by(cert, self.ca.cert))
        self.assertTrue(pki.key_matches(cert, key))
        # the subject is the mPCC's, never the CSR's
        self.assertEqual(cert.subject.get_attributes_for_oid(NameOID.COMMON_NAME)[0].value, "mprov.sys.7")
        self.assertEqual(cert.subject.get_attributes_for_oid(NameOID.ORGANIZATIONAL_UNIT_NAME)[0].value, "system")
        self.assertEqual(list(cert.extensions.get_extension_for_class(x509.ExtendedKeyUsage).value),
                         [ExtendedKeyUsageOID.CLIENT_AUTH])
        self.assertFalse(cert.extensions.get_extension_for_class(x509.BasicConstraints).value.ca)
        self.assertEqual(cert.not_valid_before_utc, (now - pki.BACKDATE).replace(microsecond=0))
        self.assertEqual(cert.not_valid_after_utc, (now + datetime.timedelta(days=30)).replace(microsecond=0))

    def test_never_outlives_the_ca(self):
        cert = self.ca.sign_csr(check_csr(make_csr()), "x", "system", datetime.timedelta(days=99999))
        self.assertLessEqual(cert.not_valid_after_utc, self.ca.cert.not_valid_after_utc)
