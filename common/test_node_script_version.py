import importlib.util
import sys
from pathlib import Path
from unittest import mock

from django.conf import settings
from django.contrib.auth.models import User
from django.test import SimpleTestCase, TestCase, override_settings
from rest_framework_api_key.models import APIKey

from mprov_control_center.version import API_VERSION
from systems.models import NetworkInterface, System


def load(name):
    path = Path(settings.BASE_DIR) / "static" / name
    spec = importlib.util.spec_from_file_location(f"{name}_under_test", path)
    module = importlib.util.module_from_spec(spec)
    # the stateful installer imports pyparted and sh, which the mPCC doesn't have
    with mock.patch.dict(sys.modules, {"parted": mock.MagicMock(), "sh": mock.MagicMock()}):
        spec.loader.exec_module(module)
    return module


class Reply:
    def __init__(self, headers):
        self.headers = headers


class LearnVersionTests(SimpleTestCase):
    """ #520: the mPCC's own node scripts send its API version. """

    def test_both_scripts(self):
        for name in ("genNetworkInterfaces.py", "mprov_stateful.py"):
            with self.subTest(script=name):
                module = load(name)
                session = mock.MagicMock()
                session.headers = {}
                session.get.return_value = Reply({"mProv-Version": "0.7"})
                self.assertEqual(module.learn_mprov_version(session, "https://10.0.0.1/"), "0.7")
                self.assertEqual(session.headers["mProv-Version"], "0.7")
                url, = session.get.call_args.args
                self.assertEqual(url, "https://10.0.0.1/enroll/ca.crt")
                self.assertEqual(session.get.call_args.kwargs["headers"], {"Authorization": None})

    def test_an_mpcc_without_the_lock_or_unreachable(self):
        module = load("genNetworkInterfaces.py")
        session = mock.MagicMock()
        session.headers = {}
        session.get.return_value = Reply({})
        self.assertIsNone(module.learn_mprov_version(session, "http://10.0.0.1/"))
        session.get.side_effect = OSError("no route to host")
        self.assertIsNone(module.learn_mprov_version(session, "http://10.0.0.1/"))
        self.assertNotIn("mProv-Version", session.headers)

    def test_start_session_learns_it_first(self):
        for name, cls in (("genNetworkInterfaces.py", "mProvNetworkScriptGenerator"),
                          ("mprov_stateful.py", "mProvStatefulInstaller")):
            with self.subTest(script=name):
                module = load(name)
                klass = getattr(module, cls, None)
                if klass is None:
                    self.skipTest(f"{name} has no {cls}")
                obj = klass.__new__(klass)
                obj.mprovURL, obj.apikey, obj.caBundle, obj.heartbeatInterval = "http://10.0.0.1/", "k", None, 0
                obj.session = mock.MagicMock()
                obj.session.headers = {}
                calls = []
                obj.session.get.side_effect = lambda url, **kw: calls.append(url) or Reply({"mProv-Version": "0.7"})
                with mock.patch.object(module, "mprov_enroll", None), mock.patch.object(module.socket, "fromfd"):
                    try:
                        obj.startSession()
                    except Exception:
                        pass  # whatever follows the first calls isn't under test here
                self.assertEqual(calls[:2], ["http://10.0.0.1/enroll/ca.crt", "http://10.0.0.1/"])
                self.assertEqual(obj.session.headers["mProv-Version"], "0.7")


# the shared key, as an older image's node still uses it
@override_settings(MPROV_SKIP_VERSION_CHECK=False, MPROV_SHARED_KEY_MODE="all")
class MiddlewareTests(TestCase):
    """ What the scripts rely on: /enroll/ca.crt carries the version for
    anyone, and a node that sends it gets no warning. """

    def setUp(self):
        user = User.objects.create_superuser("admin", "a@x", "pw")
        system = System.objects.create(hostname="c01", created_by=user)
        NetworkInterface.objects.create(system=system, name="eth0", ipaddress="10.0.0.20")
        _, self.key = APIKey.objects.create_key(name="shared")

    def test_the_version_is_on_ca_crt_for_anyone(self):
        response = self.client.get("/enroll/ca.crt", REMOTE_ADDR="10.0.0.20", HTTP_AUTHORIZATION=f"Api-Key {self.key}")
        self.assertNotEqual(response.status_code, 426)
        self.assertEqual(response["mProv-Version"], API_VERSION)

    def test_no_warning_once_the_node_sends_it(self):
        with self.assertNoLogs("mprov.version", "WARNING"):
            response = self.client.get("/systems/?self", REMOTE_ADDR="10.0.0.20", CONTENT_TYPE="application/json",
                                       HTTP_AUTHORIZATION=f"Api-Key {self.key}", HTTP_MPROV_VERSION=API_VERSION)
        self.assertEqual(response.status_code, 200, response.content)
        with self.assertLogs("mprov.version", "WARNING"):
            self.client.get("/systems/?self", REMOTE_ADDR="10.0.0.20", CONTENT_TYPE="application/json",
                            HTTP_AUTHORIZATION=f"Api-Key {self.key}")
