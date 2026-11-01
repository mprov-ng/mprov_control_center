from django.test import SimpleTestCase, override_settings
from rest_framework_api_key.models import APIKey

from common.testing import APITestCase
from common.version import major_minor
from mprov_control_center.version import API_VERSION, __version__
from networks.models import Network, NetworkType
from systems.models import NetworkInterface, System

OLD = "0.5"


class MajorMinorTests(SimpleTestCase):

  def test_versions(self):
    for value, expected in (("0.6", "0.6"), ("0.6.2", "0.6"), (" 1.10.0 ", "1.10"), ("00.6", "0.6"),
                            ("0", None), ("abc", None), ("0.x", None), ("", None), (None, None)):
      with self.subTest(value=value):
        self.assertEqual(major_minor(value), expected)

  def test_api_version_is_the_release_major_minor(self):
    self.assertEqual(API_VERSION, ".".join(__version__.split(".")[:2]))


class APIVersionTestCase(APITestCase):
  """ The mProv-Version lock on API-key requests (#452). """

  def setUp(self):
    super().setUp()
    self.client.logout()
    _, self.key = APIKey.objects.create_key(name="version-test")
    net_type = NetworkType.objects.create(name="Ethernet")
    self.lan = Network.objects.create(name="lan", net_type=net_type, subnet="10.0.0.0", netmask=24)
    self.node = System.objects.create(hostname="node01", created_by=self.user)
    NetworkInterface.objects.create(system=self.node, name="ens18", ipaddress="10.0.0.11", network=self.lan)

  def api(self, url, version=API_VERSION, client="192.0.2.1", method="get", **extra):
    headers = {"HTTP_AUTHORIZATION": f"Api-Key {self.key}", "REMOTE_ADDR": client, **extra}
    if version is not None:
      headers["HTTP_MPROV_VERSION"] = version
    return getattr(self.client, method)(url, CONTENT_TYPE="application/json", **headers)


class APIVersionCheckTests(APIVersionTestCase):

  def test_matching_version_passes(self):
    for version in (API_VERSION, __version__, API_VERSION + ".9"):
      with self.subTest(version=version):
        response = self.api("/systems/", version=version)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["mProv-Version"], API_VERSION)

  def test_another_version_is_426(self):
    response = self.api("/systems/", version=OLD)
    self.assertEqual(response.status_code, 426)
    self.assertEqual(response["mProv-Version"], API_VERSION)
    body = response.json()
    self.assertEqual((body["expected"], body["got"]), (API_VERSION, OLD))
    self.assertIn("mismatch", body["detail"])

  def test_a_missing_or_garbled_version_is_426(self):
    for version in (None, "", "latest"):
      with self.subTest(version=version):
        response = self.api("/jobservers/", version=version, method="post")
        self.assertEqual(response.status_code, 426)
        self.assertEqual(response.json()["got"], version)

  def test_browser_sessions_and_unauthenticated_requests_arent_checked(self):
    # anonymous: the index (the container health check) and a node's iPXE fetch.
    for url in ("/", "/ipxe/"):
      with self.subTest(url=url):
        response = self.client.get(url)
        self.assertNotEqual(response.status_code, 426)
        self.assertEqual(response["mProv-Version"], API_VERSION)
    self.client.force_login(self.user)
    response = self.client.get("/systems/", CONTENT_TYPE="application/json")
    self.assertEqual(response.status_code, 200)
    self.assertEqual(response["mProv-Version"], API_VERSION)
    self.assertEqual(self.client.get("/admin/")["mProv-Version"], API_VERSION)

  def test_errors_carry_the_version_too(self):
    response = self.api("/systems/999999/")
    self.assertEqual(response.status_code, 404)
    self.assertEqual(response["mProv-Version"], API_VERSION)

  def test_a_job_servers_first_request_gets_the_version(self):
    """ mprov_jobserver's startSession() opens with GET / (an exempt endpoint)
    and treats a reply without mProv-Version as a mismatch, so every reply
    to it must carry the header: from a job server's address (not a known
    system), and from a node's address, with the right version or none. """
    for client, version in (("192.0.2.1", API_VERSION), ("10.0.0.11", API_VERSION), ("10.0.0.11", None)):
      with self.subTest(client=client, version=version):
        response = self.api("/", version=version, client=client)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["mProv-Version"], API_VERSION)
    # with no version, from anywhere else, it's refused, and says which version it wants.
    response = self.api("/", version=None, client="192.0.2.1")
    self.assertEqual(response.status_code, 426)
    self.assertEqual(response["mProv-Version"], API_VERSION)

  def test_a_server_error_carries_the_version(self):
    from unittest import mock
    self.client.raise_request_exception = False
    with mock.patch("mprov_control_center.views.IndexAPIView.get", side_effect=RuntimeError("boom")):
      response = self.api("/")
    self.assertEqual(response.status_code, 500)
    self.assertEqual(response["mProv-Version"], API_VERSION)

  @override_settings(MPROV_SKIP_VERSION_CHECK=True)
  def test_the_escape_hatch_turns_the_check_off(self):
    response = self.api("/systems/", version=OLD)
    self.assertEqual(response.status_code, 200)
    self.assertEqual(response["mProv-Version"], API_VERSION)


class APIVersionExemptionTests(APIVersionTestCase):
  """ Baked node scripts' endpoints pass from a known system's address. """

  def test_a_node_script_endpoint_from_a_node_passes_and_warns(self):
    for url, method in (("/systems/?self", "get"), (f"/systembmcs/?system={self.node.pk}&detail", "get"),
                        (f"/networks/{self.lan.pk}/", "get"), ("/", "get")):
      with self.subTest(url=url):
        with self.assertLogs("mprov.version", "WARNING") as logs:
          response = getattr(self, "api")(url, version=OLD, client="10.0.0.11", method=method)
        self.assertNotEqual(response.status_code, 426)
        self.assertEqual(response["mProv-Version"], API_VERSION)
        self.assertIn("10.0.0.11", logs.output[0])
        self.assertIn(OLD, logs.output[0])

  def test_a_missing_version_from_a_node_passes_and_warns(self):
    with self.assertLogs("mprov.version", "WARNING") as logs:
      response = self.api("/systems/?self", version=None, client="10.0.0.11")
    self.assertEqual(response.status_code, 200)
    self.assertIn("not sent", logs.output[0])

  def test_the_same_endpoint_from_anywhere_else_is_426(self):
    # an outdated job server or mash isn't exempt (decided on #452).
    self.assertEqual(self.api("/systems/?self", version=OLD, client="192.0.2.1").status_code, 426)
    self.assertEqual(self.api(f"/networks/{self.lan.pk}/", version=OLD, client="192.0.2.1").status_code, 426)

  def test_other_endpoints_from_a_node_are_426(self):
    for url in ("/systems/", "/jobservers/", "/networks/", f"/systems/{self.node.pk}/"):
      with self.subTest(url=url):
        self.assertEqual(self.api(url, version=OLD, client="10.0.0.11").status_code, 426)

  @override_settings(MPROV_VERSION_EXEMPT=[])
  def test_the_list_comes_from_settings(self):
    self.assertEqual(self.api("/systems/?self", version=OLD, client="10.0.0.11").status_code, 426)

  @override_settings(MPROV_VERSION_EXEMPT=["jobs/<pk>/", "systems/?hostname"])
  def test_pk_and_query_key_patterns(self):
    with self.assertLogs("mprov.version", "WARNING"):
      self.assertNotEqual(self.api("/jobs/1/", version=OLD, client="10.0.0.11").status_code, 426)
      self.assertNotEqual(self.api("/systems/?hostname=node01", version=OLD, client="10.0.0.11").status_code, 426)
    self.assertEqual(self.api("/jobs/", version=OLD, client="10.0.0.11").status_code, 426)
    self.assertEqual(self.api("/jobs/1/claim/", version=OLD, client="10.0.0.11", method="post").status_code, 426)
    self.assertEqual(self.api("/systems/?self", version=OLD, client="10.0.0.11").status_code, 426)


class APIVersionDocsTests(APITestCase):

  def test_the_index_documents_it(self):
    self.assertContains(self.client.get("/"), "API versioning")
