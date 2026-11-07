import datetime
import importlib.util
import json
import os
import re
import stat
import tempfile
from pathlib import Path
from unittest import mock

from cryptography import x509
from django.conf import settings
from django.test import SimpleTestCase

from pki.ca import CA, cert_pem, check_csr, fingerprint
from pki.models import AgentCredential, BootNonce
from pki.signer_client import local_signer
from pki.test_auth import AgentTestCase
from pki.test_ca import make_csr
from pki.test_enroll import EnrollTestCase
from pki.views import EnrollBase
from systems.models import SystemImage


def load_enroll_module():
    path = Path(settings.BASE_DIR) / "static" / "mprov_enroll.py"
    spec = importlib.util.spec_from_file_location("mprov_enroll_under_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Reply:
    def __init__(self, status, text="", body=None):
        self.status_code, self.text, self._body = status, text, body

    def json(self):
        return self._body

    def raise_for_status(self):
        if self.status_code >= 400:
            raise ValueError(f"HTTP {self.status_code}")


class FakeSession:
    """ The mPCC as a node sees it: /enroll/ca.crt over HTTP, /enroll/system/ over HTTPS. """

    def __init__(self, ca, enroll_status=200):
        self.ca, self.enroll_status, self.headers, self.posts = ca, enroll_status, {"Authorization": "Api-Key x"}, []

    def get(self, url, **kwargs):
        assert url.endswith("/enroll/ca.crt"), url
        assert kwargs["headers"] == {"Authorization": None}
        return Reply(200, cert_pem(self.ca.cert))

    def post(self, url, data, **kwargs):
        self.posts.append((url, json.loads(data), kwargs))
        if self.enroll_status != 200:
            return Reply(self.enroll_status, "refused")
        cert = self.ca.sign_csr(check_csr(json.loads(data)["csr"]), "mprov.sys.1", "system", datetime.timedelta(days=1))
        return Reply(200, body={"certificate": cert_pem(cert)})


class NodeEnrollModuleTests(SimpleTestCase):
    """ #381: static/mprov_enroll.py, which the node's boot scripts enroll with. """

    def setUp(self):
        self.m = load_enroll_module()
        self.ca = CA.create("test CA")
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(__import__("shutil").rmtree, self.tmp, True)
        self.tls = os.path.join(self.tmp, "tls")
        self.cmdline = os.path.join(self.tmp, "cmdline")
        self.write_cmdline(f"quiet mprov_enroll={'a' * 32} mprov_ca={fingerprint(self.ca.cert)} mprov_rescue=0")
        self.log = []

    def write_cmdline(self, text):
        with open(self.cmdline, "w") as f:
            f.write(text + "\n")

    def enroll(self, session):
        return self.m.enroll(session, "http://10.0.0.1/", cmdline=self.cmdline, tls_dir=self.tls, log=self.log.append)

    def test_kernel_params(self):
        self.assertEqual(self.m.kernel_params(self.cmdline), ("a" * 32, fingerprint(self.ca.cert)))
        for text in ("quiet", "mprov_enroll=xyz mprov_ca=abc", f"mprov_enroll={'a' * 32}"):
            with self.subTest(text=text):
                self.write_cmdline(text)
                self.assertIn(None, self.m.kernel_params(self.cmdline))
        self.assertEqual(self.m.kernel_params(os.path.join(self.tmp, "nope")), (None, None))

    def test_https_url(self):
        for url, expected in (("http://10.0.0.1/", "https://10.0.0.1/"), ("http://mpcc:8080/", "https://mpcc/"),
                              ("http://mpcc", "https://mpcc/"), ("http://[fd00::1]:80/", "https://[fd00::1]/")):
            with self.subTest(url=url):
                self.assertEqual(self.m.https_url(url), expected)

    def test_pem_fingerprint_matches_the_mpccs(self):
        self.assertEqual(self.m.pem_fingerprint(cert_pem(self.ca.cert)), fingerprint(self.ca.cert))

    def test_enrolls(self):
        session = FakeSession(self.ca)
        self.assertTrue(self.enroll(session))
        url, body, kwargs = session.posts[0]
        self.assertEqual(url, "https://10.0.0.1/enroll/system/")
        self.assertEqual(body["nonce"], "a" * 32)
        self.assertEqual(kwargs["headers"]["Authorization"], None)
        self.assertTrue(kwargs["verify"].endswith("ca.crt"))
        self.assertTrue(self.m.have(self.tls))
        self.assertEqual(stat.S_IMODE(os.stat(os.path.join(self.tls, "node.key")).st_mode), 0o600)
        with open(os.path.join(self.tls, "node.crt"), "rb") as f:
            cert = x509.load_pem_x509_certificate(f.read())
        with open(os.path.join(self.tls, "node.key"), "rb") as f:
            from cryptography.hazmat.primitives import serialization
            key = serialization.load_pem_private_key(f.read(), password=None)
        from pki.ca import key_matches
        self.assertTrue(key_matches(cert, key))
        self.assertEqual(sorted(os.listdir(self.tls)), ["ca.crt", "node.crt", "node.key"])

    def test_no_params_means_the_shared_key(self):
        self.write_cmdline("quiet")
        self.assertFalse(self.enroll(FakeSession(self.ca)))
        self.assertFalse(os.path.exists(self.tls))

    def test_a_ca_that_doesnt_match_is_never_trusted(self):
        session = FakeSession(CA.create("impostor"))
        self.assertFalse(self.enroll(session))
        self.assertEqual(session.posts, [])
        self.assertIn("doesn't match", self.log[-1])

    def test_a_refusal_leaves_nothing_behind(self):
        self.assertFalse(self.enroll(FakeSession(self.ca, enroll_status=403)))
        self.assertFalse(self.m.have(self.tls))
        self.assertEqual(os.listdir(self.tls), [])

    def test_use(self):
        session = FakeSession(self.ca)
        url = self.m.use(session, "http://10.0.0.1/", tls_dir=self.tls)
        self.assertEqual(url, "https://10.0.0.1/")
        self.assertEqual(session.cert, (os.path.join(self.tls, "node.crt"), os.path.join(self.tls, "node.key")))
        self.assertEqual(session.verify, os.path.join(self.tls, "ca.crt"))
        self.assertNotIn("Authorization", session.headers)


class BootScriptsTests(SimpleTestCase):
    """ #381: the boot scripts enroll when they can, and fall back to the shared key. """

    def test_boot_init_downloads_the_module_next_to_the_scripts(self):
        script = (Path(settings.BASE_DIR) / "static" / "mprov_boot_init.sh").read_text()
        download = script.index("/image/tmp/mprov_enroll.py")
        self.assertLess(download, script.index("/tmp/mprov_genNetworkInterfaces.py\n"))

    def test_gen_network_interfaces_switches_to_its_credential(self):
        path = Path(settings.BASE_DIR) / "static" / "genNetworkInterfaces.py"
        spec = importlib.util.spec_from_file_location("gni_under_test", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        gen = module.mProvNetworkScriptGenerator.__new__(module.mProvNetworkScriptGenerator)
        gen.mprovURL, gen.apikey = "http://10.0.0.1/", "k"
        gen.session = mock.MagicMock()
        fake = mock.MagicMock()
        fake.enroll.return_value = True
        fake.use.return_value = "https://10.0.0.1/"
        with mock.patch.object(module, "mprov_enroll", fake), mock.patch.object(module.socket, "fromfd"):
            gen.startSession()
        self.assertEqual(gen.mprovURL, "https://10.0.0.1/")
        gen.session.get.assert_called_with("https://10.0.0.1/", stream=True)

    def test_gen_network_interfaces_without_the_module(self):
        path = Path(settings.BASE_DIR) / "static" / "genNetworkInterfaces.py"
        spec = importlib.util.spec_from_file_location("gni_under_test2", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        gen = module.mProvNetworkScriptGenerator.__new__(module.mProvNetworkScriptGenerator)
        gen.mprovURL, gen.apikey = "http://10.0.0.1/", "k"
        gen.session = mock.MagicMock()
        with mock.patch.object(module, "mprov_enroll", None), mock.patch.object(module.socket, "fromfd"):
            gen.startSession()
        self.assertEqual(gen.mprovURL, "http://10.0.0.1/")


class BuildCredentialTests(AgentTestCase):
    """ #381: a job server gets a 2-hour credential for the script runner in an image it builds. """

    def setUp(self):
        super().setUp()
        patcher = mock.patch.object(EnrollBase, "signer", staticmethod(local_signer(self.ca)))
        patcher.start()
        self.addCleanup(patcher.stop)
        self.other = SystemImage.objects.create(name="other", created_by=self.admin)

    def get_build(self, pem=None, image=None, ip="10.0.0.5"):
        return self.call("POST", "/enroll/build/", {"csr": make_csr().decode(), "image": image or self.image.slug},
                         pem=pem or self.js_pem, ip=ip, secure=True)

    def test_issued_for_two_hours_and_reads_only_its_image(self):
        response = self.get_build()
        self.assertEqual(response.status_code, 200, response.content)
        pem = response.json()["certificate"]
        cert = x509.load_pem_x509_certificate(pem.encode())
        self.assertLessEqual(cert.not_valid_after_utc - cert.not_valid_before_utc, datetime.timedelta(hours=3))
        credential = AgentCredential.objects.get(fingerprint=fingerprint(cert))
        self.assertEqual((credential.kind, credential.image), ("build", self.image))
        self.assertEqual(credential.user.username, f"mprov.build.{self.image.slug}")
        # from anywhere (the job server's chroot), but only its own image
        self.assertEqual(self.call("GET", f"/systemimages/{self.image.slug}/", pem=pem, ip="10.9.9.9").status_code, 200)
        self.assertEqual(self.call("GET", f"/systemimages/{self.other.slug}/", pem=pem).status_code, 403)
        for url in ("/systems/", "/systembmcs/", "/jobs/"):
            self.assertEqual(self.call("GET", url, pem=pem).status_code, 403)
        self.assertEqual(self.call("POST", "/enroll/renew/", {"csr": make_csr().decode()}, pem=pem,
                                   secure=True).status_code, 403)

    def test_only_a_job_server_gets_one(self):
        self.assertEqual(self.get_build(pem=self.c01_pem, ip="10.0.0.20").status_code, 403)

    def test_bad_requests(self):
        self.assertEqual(self.get_build(image="nope").status_code, 400)
        response = self.call("POST", "/enroll/build/", {"csr": make_csr().decode(), "image": self.image.slug},
                             pem=self.js_pem, ip="10.0.0.5")
        self.assertEqual(response.status_code, 403)  # not HTTPS


class CustomIPXETests(EnrollTestCase):
    """ #381: an image's custom iPXE script builds its own kernel command line,
    so it gets the enrollment parameters as {{ boot.enroll }}. """

    def script(self, text):
        SystemImage.objects.filter(pk=self.image.pk).update(customIPXE=text)
        return self.client.get("/ipxe/", REMOTE_ADDR="10.0.0.20").content.decode()

    def test_a_script_that_uses_them_can_enroll(self):
        content = self.script("#!ipxe\nkernel http://x/vmlinuz {{ boot.install_kernel_cmdline }} {{ boot.enroll }}\n")
        nonce = re.search(r"mprov_enroll=([0-9a-f]{32})", content).group(1)
        self.assertIn(f"mprov_ca={fingerprint(self.ca.cert)}\n", content)
        response = self.post("/enroll/system/", {"nonce": nonce, "csr": make_csr().decode()})
        self.assertEqual(response.status_code, 200, response.content)

    def test_no_nonce_unless_the_script_uses_it(self):
        self.assertNotIn("mprov_enroll", self.script("#!ipxe\nkernel http://x/vmlinuz quiet\n"))
        self.assertFalse(BootNonce.objects.exists())
