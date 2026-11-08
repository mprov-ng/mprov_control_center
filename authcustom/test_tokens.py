import base64
import datetime
from io import StringIO

from django.contrib.auth.models import Permission, User
from django.core.management import CommandError, call_command
from django.test import TestCase, override_settings
from django.utils import timezone

from authcustom.models import UserToken
from jobqueue.models import Job, JobModule, JobServer, JobStatus
from mprov_control_center.version import API_VERSION
from networks.models import Network, NetworkType
from systems.models import System, SystemBMC


@override_settings(MPROV_SKIP_VERSION_CHECK=False)
class APITestCase(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser("admin", "a@example.com", "pw")
        self.staff = User.objects.create_user("ops", "o@example.com", "pw", is_staff=True)
        self.node = System.objects.create(hostname="c01", created_by=self.admin)

    def headers(self, auth, version=True):
        meta = {"HTTP_AUTHORIZATION": auth, "CONTENT_TYPE": "application/json"}
        if version:
            meta["HTTP_MPROV_VERSION"] = API_VERSION
        return meta

    @staticmethod
    def basic(username, password="pw"):
        return "Basic " + base64.b64encode(f"{username}:{password}".encode()).decode()

    def call(self, method, url, auth, body=None, version=True):
        kwargs = self.headers(auth, version)
        if body is not None:
            return getattr(self.client, method.lower())(url, body, content_type="application/json", **{
                k: v for k, v in kwargs.items() if k != "CONTENT_TYPE"})
        return getattr(self.client, method.lower())(url, **kwargs)

    def grant(self, user, *codenames):
        for codename in codenames:
            app, name = codename.split(".")
            user.user_permissions.add(Permission.objects.get(content_type__app_label=app, codename=name))
        # drop the cached permissions
        return User.objects.get(pk=user.pk)


class TokenAuthTests(APITestCase):
    """ #502: Authorization: Token <token> acts as its user. """

    def setUp(self):
        super().setUp()
        self.token, self.secret = UserToken.make(self.admin, "laptop")

    def get(self, secret=None, version=True, url="/systems/"):
        return self.call("GET", url, f"Token {secret or self.secret}", version=version)

    def test_acts_as_its_user(self):
        self.assertEqual(self.get().status_code, 200)
        response = self.call("POST", "/systemgroups/", f"Token {self.secret}", {"name": "rack1"})
        self.assertEqual(response.status_code, 201, response.content)

    def test_records_its_last_use(self):
        self.assertIsNone(self.token.last_used)
        self.get()
        first = UserToken.objects.get(pk=self.token.pk).last_used
        self.assertIsNotNone(first)
        self.get()
        self.assertEqual(UserToken.objects.get(pk=self.token.pk).last_used, first)  # at most once a minute

    def test_refusals_say_why(self):
        cases = []
        cases.append(("Unknown token.", "nope.nope"))
        cases.append(("Unknown token.", self.token.prefix + ".wrong"))
        revoked, revoked_secret = UserToken.make(self.admin, "old")
        revoked.revoked = True
        revoked.save()
        cases.append(("This token was revoked.", revoked_secret))
        expired, expired_secret = UserToken.make(self.admin, "short", days=1)
        UserToken.objects.filter(pk=expired.pk).update(expiry_date=timezone.now() - datetime.timedelta(days=1))
        cases.append(("This token expired on", expired_secret))
        _, staff_secret = UserToken.make(self.staff, "ops")
        cases.append((None, staff_secret))
        for message, secret in cases[:-1]:
            with self.subTest(message=message):
                response = self.get(secret)
                self.assertEqual(response.status_code, 401)
                self.assertIn(message, response.json()["detail"])
        # a user who stops being staff, or is disabled, loses their tokens
        User.objects.filter(pk=self.staff.pk).update(is_staff=False)
        self.assertIn("isn't staff", self.get(staff_secret).json()["detail"])
        User.objects.filter(pk=self.staff.pk).update(is_staff=True, is_active=False)
        self.assertIn("inactive", self.get(staff_secret).json()["detail"])
        response = self.call("GET", "/systems/", "Token")
        self.assertEqual(response.status_code, 401)

    def test_version_locked(self):
        self.assertEqual(self.get(version=False).status_code, 426)

    def test_not_a_shared_key(self):
        self.assertIn(self.call("GET", "/systems/", f"Api-Key {self.secret}").status_code, (401, 403))


class TokensEndpointTests(APITestCase):
    """ #502: /tokens/ for mash's connect … --save-token; staff only. """

    def test_make_with_a_password(self):
        response = self.call("POST", "/tokens/", self.basic("ops"), {"name": "mash on laptop", "days": 30})
        self.assertEqual(response.status_code, 201, response.content)
        body = response.json()
        token = UserToken.objects.get(prefix=body["prefix"])
        self.assertEqual((token.user, token.name), (self.staff, "mash on laptop"))
        self.assertAlmostEqual(token.expiry_date, timezone.now() + datetime.timedelta(days=30),
                               delta=datetime.timedelta(minutes=1))
        # it works, with ops' permissions
        self.assertEqual(self.call("GET", "/tokens/", f"Token {body['token']}").status_code, 200)

    def test_not_with_a_token(self):
        _, secret = UserToken.make(self.staff, "first")
        response = self.call("POST", "/tokens/", f"Token {secret}", {"name": "second"})
        self.assertEqual(response.status_code, 403)

    def test_staff_only(self):
        User.objects.create_user("viewer", "v@example.com", "pw")
        self.assertEqual(self.call("POST", "/tokens/", self.basic("viewer"), {"name": "x"}).status_code, 403)

    def test_bad_requests(self):
        for body in ({}, {"name": ""}, {"name": "x" * 51}, {"name": "x", "days": 0}, {"name": "x", "days": "7"},
                     {"name": "x", "days": True}):
            with self.subTest(body=body):
                self.assertEqual(self.call("POST", "/tokens/", self.basic("ops"), body).status_code, 400)

    def test_list_and_revoke_your_own(self):
        mine, _ = UserToken.make(self.staff, "mine")
        theirs, _ = UserToken.make(self.admin, "theirs")
        listing = self.call("GET", "/tokens/", self.basic("ops")).json()
        self.assertEqual([t["prefix"] for t in listing], [mine.prefix])
        self.assertNotIn("token", listing[0])
        self.assertEqual(self.call("DELETE", f"/tokens/{theirs.prefix}/", self.basic("ops")).status_code, 404)
        self.assertEqual(self.call("DELETE", f"/tokens/{mine.prefix}/", self.basic("ops")).status_code, 204)
        self.assertTrue(UserToken.objects.get(pk=mine.pk).revoked)


class TokenAdminAndCommandTests(APITestCase):
    """ #502: the API Tokens admin page and manage.py mprov_token. """

    def test_staff_make_their_own_in_the_admin(self):
        self.client.force_login(self.staff)
        response = self.client.post("/admin/authcustom/usertoken/add/", {"name": "ci", "days": ""}, follow=True)
        token = UserToken.objects.get()
        self.assertEqual((token.user, token.expiry_date), (self.staff, None))
        self.assertContains(response, "shown only this once")
        UserToken.make(self.admin, "admin's")
        page = self.client.get("/admin/authcustom/usertoken/").content.decode()
        self.assertIn("ci", page)
        self.assertNotIn("admin&#x27;s", page)
        self.client.post("/admin/authcustom/usertoken/", {"action": "revoke", "_selected_action": [token.pk]})
        self.assertTrue(UserToken.objects.get(pk=token.pk).revoked)

    def test_command(self):
        out = StringIO()
        call_command("mprov_token", "create", "--user", "ops", "--name", "script", "--days", "7", stdout=out)
        secret = out.getvalue().strip()
        self.assertEqual(self.call("GET", "/tokens/", f"Token {secret}").status_code, 200)
        out = StringIO()
        call_command("mprov_token", "list", "--user", "ops", stdout=out)
        self.assertIn("script\tactive", out.getvalue())
        self.assertNotIn(secret.split(".")[1], out.getvalue())
        call_command("mprov_token", "revoke", secret.split(".")[0], stdout=StringIO())
        self.assertEqual(self.call("GET", "/tokens/", f"Token {secret}").status_code, 401)
        User.objects.create_user("viewer", "v@example.com", "pw")
        with self.assertRaises(CommandError):
            call_command("mprov_token", "create", "--user", "viewer", "--name", "x", stdout=StringIO())


class ModelPermissionTests(APITestCase):
    """ #502: a person gets their own Django model permissions; a superuser everything. """

    def setUp(self):
        super().setUp()
        _, self.staff_secret = UserToken.make(self.staff, "ops")

    def as_staff(self, method, url, body=None, basic=False):
        auth = self.basic("ops") if basic else f"Token {self.staff_secret}"
        return self.call(method, url, auth, body)

    def test_crud_maps_to_model_permissions(self):
        response = self.as_staff("GET", "/systems/")
        self.assertEqual(response.status_code, 403)
        self.assertIn("ops needs the permission systems.view_system", response.json()["detail"])
        self.grant(self.staff, "systems.view_system")
        self.assertEqual(self.as_staff("GET", "/systems/").status_code, 200)
        self.assertEqual(self.as_staff("GET", "/systems/", basic=True).status_code, 200)
        self.assertEqual(self.as_staff("PATCH", f"/systems/{self.node.pk}/", {"hostname": "c99"}).status_code, 403)
        self.grant(self.staff, "systems.change_system")
        self.assertEqual(self.as_staff("PATCH", f"/systems/{self.node.pk}/", {"hostname": "c99"}).status_code, 200)
        self.assertEqual(self.as_staff("DELETE", f"/systems/{self.node.pk}/").status_code, 403)
        self.grant(self.staff, "systems.delete_system")
        self.assertEqual(self.as_staff("DELETE", f"/systems/{self.node.pk}/").status_code, 204)

    def test_a_session_too(self):
        self.client.force_login(self.staff)
        response = self.client.get("/systembmcs/", CONTENT_TYPE="application/json")
        self.assertEqual(response.status_code, 403)

    def test_superusers_do_everything(self):
        _, secret = UserToken.make(self.admin, "admin")
        for url in ("/systems/", f"/systems/{self.node.pk}/"):
            self.assertEqual(self.call("GET", url, f"Token {secret}").status_code, 200, url)
        self.assertEqual(self.call("DELETE", f"/systems/{self.node.pk}/", f"Token {secret}").status_code, 204)

    def test_power_actions(self):
        SystemBMC.objects.create(system=self.node, ipaddress="10.0.1.1", username="u", password="p")
        self.assertEqual(self.as_staff("GET", "/power/status/").status_code, 403)
        self.grant(self.staff, "systems.view_systembmc")
        self.assertEqual(self.as_staff("GET", "/power/status/").status_code, 400)  # no filter, but allowed
        response = self.as_staff("GET", "/power/on/")
        self.assertEqual(response.status_code, 403)
        self.assertIn("systems.change_system", response.json()["detail"])
        self.grant(self.staff, "systems.change_system")
        self.assertEqual(self.as_staff("GET", "/power/on/").status_code, 400)

    def test_declared_views(self):
        js = JobServer.objects.create(name="js1", host_id="h1")
        module = JobModule.objects.create(slug="image-update", name="Image Update")
        for pk, name in ((1, "Pending"), (2, "Running"), (3, "Success"), (4, "Failed")):
            JobStatus.objects.get_or_create(pk=pk, defaults={"name": name})
        job = Job.objects.create(name="j", module=module, status=JobStatus.objects.get(pk=1))
        self.assertIn("jobqueue.change_job", self.as_staff("POST", f"/jobs/{job.pk}/claim/", {"jobserver": js.pk})
                      .json()["detail"])
        self.assertIn("jobqueue.change_jobserver",
                      self.as_staff("POST", f"/jobservers/{js.pk}/heartbeat/", {"address": "10.0.0.5"}).json()["detail"])
        net = Network.objects.create(name="n", slug="n", net_type=NetworkType.objects.create(name="Ethernet"),
                                     subnet="10.1.0.0", netmask=24)
        self.grant(self.staff, "networks.change_network")
        response = self.as_staff("POST", f"/networks/{net.pk}/update-with-confirmation/", {})
        self.assertEqual(response.status_code, 403)
        self.assertIn("systems.change_networkinterface", response.json()["detail"])
        self.assertIn("networks.view_network",
                      self.as_staff("GET", f"/networks/{net.pk}/preview-subnet-changes/").json()["detail"])

    def test_no_model_means_superusers_only(self):
        response = self.as_staff("POST", "/enroll/build/", {})
        self.assertIn(response.status_code, (403,))
