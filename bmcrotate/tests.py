import datetime

from django.contrib.admin.models import LogEntry
from django.utils import timezone

from bmcrotate import logic
from bmcrotate.models import BMCRotation
from jobqueue.models import Job, JobModule, JobServerAddress, JobStatus
from pki.issue import issue_credential
from pki.test_auth import DAY, AgentTestCase
from pki.test_ca import make_csr
from systems.models import SystemBMC


class BMCRotationTestCase(AgentTestCase):
    """ #486: changing BMC credentials on the BMCs through a bmc-rotate job. """

    def setUp(self):
        super().setUp()
        for pk, name in ((1, "Pending"), (2, "Running"), (3, "Failed"), (4, "Success")):
            JobStatus.objects.get_or_create(pk=pk, defaults={"name": name})
        # made when a job server that runs it registers (#256)
        self.module, _ = JobModule.objects.get_or_create(slug="bmc-rotate", defaults={"name": "bmc-rotate"})
        self.js.jobmodules.add(self.module)
        SystemBMC.objects.filter(pk=self.bmc1.pk).update(username="admin")
        self.bmc1.refresh_from_db()
        JobServerAddress.objects.create(jobserver=self.js, network=self.lan, address="10.0.0.5")

    def change(self, username="", password="new-secret", system=None):
        rotations, _, _ = logic.start([system or self.c01], BMCRotation.CHANGE, self.admin, username, password)
        return rotations[0]

    def claim(self, rotation, pem=None, ip="10.0.0.5", jobserver=None):
        return self.call("POST", f"/jobs/{rotation.job_id}/claim/", {"jobserver": (jobserver or self.js).pk},
                         pem=pem or self.js_pem, ip=ip)

    def secret(self, rotation, **kwargs):
        return self.call("GET", f"/bmcrotations/{rotation.pk}/secret/", pem=kwargs.pop("pem", self.js_pem),
                         ip="10.0.0.5", **kwargs)

    def result(self, rotation, **body):
        return self.call("POST", f"/bmcrotations/{rotation.pk}/result/", body, pem=self.js_pem, ip="10.0.0.5")

    def bmc(self):
        return SystemBMC.objects.get(pk=self.bmc1.pk)


class QueueTests(BMCRotationTestCase):
    def test_one_job_per_bmc_and_no_secret_in_it(self):
        rotation = self.change(username="admin2")
        job = rotation.job
        self.assertEqual((job.module_id, job.status_id), ("bmc-rotate", 1))
        self.assertEqual(job.params, {"rotation": rotation.pk, "network": self.lan.pk, "bmc": "10.0.1.20"})
        self.assertNotIn("secret", str(job.params))
        self.assertEqual((rotation.current_username, rotation.new_username, rotation.new_password),
                         ("admin", "admin2", "new-secret"))

    def test_a_blank_password_keeps_the_current_one(self):
        self.assertEqual(self.change(username="admin2", password="").new_password, "secret1")

    def test_one_open_request_per_bmc(self):
        self.change()
        rotations, skipped, busy = logic.start([self.c01], BMCRotation.CHANGE, self.admin, "", "x")
        self.assertEqual((rotations, busy), ([], [self.bmc1]))

    def test_only_on_the_bmcs_network(self):
        rotation = self.change()
        other_js_pem = issue_credential(self.ca, make_csr(), DAY, jobserver=self.js2)[1]
        response = self.claim(rotation, pem=other_js_pem, ip="10.0.0.6", jobserver=self.js2)
        self.assertEqual(response.status_code, 409)
        self.assertIn("not on this BMC's network", response.json()["detail"])
        JobServerAddress.objects.filter(jobserver=self.js).update(
            heartbeat_time=timezone.now() - datetime.timedelta(minutes=5))
        self.assertEqual(self.claim(rotation).status_code, 409)  # a stale address doesn't count
        JobServerAddress.objects.filter(jobserver=self.js).update(heartbeat_time=timezone.now())
        self.assertEqual(self.claim(rotation).status_code, 200)

    def test_a_bmc_with_no_network_goes_to_any_job_server(self):
        SystemBMC.objects.filter(pk=self.bmc1.pk).update(network=None)
        rotation = self.change()
        other_js_pem = issue_credential(self.ca, make_csr(), DAY, jobserver=self.js2)[1]
        self.assertEqual(self.claim(rotation, pem=other_js_pem, ip="10.0.0.6", jobserver=self.js2).status_code, 200)


class SecretTests(BMCRotationTestCase):
    def test_only_the_job_server_running_it(self):
        rotation = self.change(username="admin2")
        self.assertEqual(self.secret(rotation).status_code, 403)  # not claimed yet
        self.claim(rotation)
        other_js_pem = issue_credential(self.ca, make_csr(), DAY, jobserver=self.js2)[1]
        self.assertEqual(self.secret(rotation, pem=other_js_pem).status_code, 403)
        # a system's certificate, from its own address
        self.assertEqual(self.call("GET", f"/bmcrotations/{rotation.pk}/secret/", pem=self.c01_pem,
                                   ip="10.0.0.20").status_code, 403)
        self.client.force_login(self.admin)
        self.assertEqual(self.call("GET", f"/bmcrotations/{rotation.pk}/secret/").status_code, 403)  # a person
        self.client.logout()
        reply = self.secret(rotation).json()
        self.assertEqual(reply["current"], {"username": "admin", "password": "secret1"})
        self.assertEqual(reply["new"], {"username": "admin2", "password": "new-secret"})
        self.assertEqual(BMCRotation.objects.get(pk=rotation.pk).status, BMCRotation.RUNNING)


class ResultTests(BMCRotationTestCase):
    def run_change(self, **result):
        rotation = self.change(username=result.pop("username", ""))
        self.claim(rotation)
        self.secret(rotation)
        response = self.result(rotation, **result)
        self.assertEqual(response.status_code, 200, response.content)
        return BMCRotation.objects.get(pk=rotation.pk), response.json()["stored"]

    def test_stores_the_new_pair_once_verified(self):
        rotation, stored = self.run_change(username="admin2", status="succeeded", method="redfish",
                                           verified="new", tls_verified=False)
        self.assertEqual((self.bmc().username, self.bmc().password), ("admin2", "new-secret"))
        self.assertIsNotNone(self.bmc().credentials_changed)
        self.assertEqual((rotation.status, stored), (BMCRotation.SUCCEEDED, "new user and password"))
        self.assertEqual((rotation.current_password, rotation.new_password, rotation.candidates), ("", "", []))
        entry = LogEntry.objects.filter(object_id=str(self.bmc1.pk)).latest("pk")
        self.assertIn("BMC Password", entry.get_change_message())
        self.assertNotIn("new-secret", entry.change_message)

    def test_a_failed_rename_stores_the_new_password_with_the_old_user(self):
        rotation, _ = self.run_change(username="admin2", status="partial", method="ipmi", verified="password_only",
                                      error="rename refused")
        self.assertEqual((self.bmc().username, self.bmc().password), ("admin", "new-secret"))
        self.assertEqual(rotation.status, BMCRotation.PARTIAL)

    def test_a_failure_stores_nothing(self):
        rotation, _ = self.run_change(status="failed", verified="current", error="auth new-secret refused")
        self.assertEqual(self.bmc().password, "secret1")
        self.assertEqual(rotation.status, BMCRotation.FAILED)
        self.assertNotIn("new-secret", rotation.error)

    def test_nothing_verified_is_unconfirmed_and_keeps_the_candidates(self):
        rotation, _ = self.run_change(username="admin2", status="unconfirmed", verified=None)
        self.assertEqual(self.bmc().password, "secret1")
        self.assertEqual(rotation.status, BMCRotation.UNCONFIRMED)
        self.assertEqual(rotation.candidates, [{"username": "admin", "password": "secret1"},
                                               {"username": "admin", "password": "new-secret"},
                                               {"username": "admin2", "password": "new-secret"}])

    def test_refused_current_credentials_are_a_plain_failure(self):
        """ The BMC was never touched: failed, nothing kept to find. """
        rotation, stored = self.run_change(username="admin2", status="failed", verified=None,
                                           error="current credentials refused")
        self.assertEqual((rotation.status, stored, rotation.candidates), (BMCRotation.FAILED, "unchanged", []))
        self.assertEqual(self.bmc().password, "secret1")
        self.assertFalse(logic.find(rotation, self.admin))

    def test_an_unreachable_bmc_is_unchanged_too(self):
        rotation, _ = self.run_change(status="unreachable", verified=None)
        self.assertEqual((rotation.status, rotation.candidates), (BMCRotation.UNREACHABLE, []))

    def test_a_result_only_once(self):
        rotation, _ = self.run_change(status="succeeded", verified="new")
        self.assertEqual(self.result(rotation, status="failed").status_code, 409)

    def test_a_job_that_ends_without_a_result_is_unconfirmed(self):
        rotation = self.change()
        self.claim(rotation)
        job = Job.objects.get(pk=rotation.job_id)
        job.status_id = 3
        job.save()
        rotation.refresh_from_db()
        self.assertEqual(rotation.status, BMCRotation.UNCONFIRMED)
        self.assertEqual(len(rotation.candidates), 2)  # same user: old pair and new password
        self.assertEqual(self.bmc().password, "secret1")

    def test_find_which_credentials_work(self):
        rotation, _ = self.run_change(username="admin2", status="unconfirmed", verified=None)
        self.assertTrue(logic.find(rotation, self.admin))
        rotation.refresh_from_db()
        self.claim(rotation)
        reply = self.secret(rotation).json()
        self.assertEqual((reply["kind"], len(reply["candidates"])), ("find", 3))
        self.result(rotation, status="succeeded", verified="2")
        self.assertEqual((self.bmc().username, self.bmc().password), ("admin2", "new-secret"))
        self.assertEqual(BMCRotation.objects.get(pk=rotation.pk).candidates, [])

    def test_a_check_stores_nothing(self):
        rotations, _, _ = logic.start([self.c01], BMCRotation.CHECK, self.admin)
        rotation = rotations[0]
        self.claim(rotation)
        self.assertIsNone(self.secret(rotation).json()["new"])
        self.result(rotation, status="succeeded", verified="current")
        self.assertEqual(BMCRotation.objects.get(pk=rotation.pk).status, BMCRotation.SUCCEEDED)
        self.assertEqual(self.bmc().password, "secret1")


class AdminTests(BMCRotationTestCase):
    def post_form(self, **fields):
        self.client.force_login(self.admin)
        data = {"action": "set_bmc_credentials", "_selected_action": [self.c01.pk], "apply": "1", **fields}
        return self.client.post("/admin/systems/system/", data, follow=True)

    def test_change_on_the_bmcs(self):
        response = self.post_form(mode="change", username="", password="pw2", confirm="pw2")
        self.assertContains(response, "Queued a change on 1 BMCs")
        self.assertEqual(self.bmc().password, "secret1")  # nothing stored yet
        self.assertEqual(BMCRotation.objects.get().new_password, "pw2")

    def test_check_needs_no_password(self):
        self.post_form(mode="check")
        self.assertEqual(BMCRotation.objects.get().kind, BMCRotation.CHECK)

    def test_no_job_server_runs_it(self):
        self.js.jobmodules.remove(self.module)
        response = self.post_form(mode="change", password="pw2", confirm="pw2")
        self.assertContains(response, "No job server runs the bmc-rotate module")
        self.assertFalse(BMCRotation.objects.exists())

    def test_store_only_is_unchanged(self):
        self.post_form(mode="store", password="pw2", confirm="pw2")
        self.assertEqual(self.bmc().password, "pw2")
        self.assertFalse(BMCRotation.objects.exists())

    def test_report_never_shows_a_password(self):
        self.change(username="admin2")
        self.client.force_login(self.admin)
        page = self.client.get("/admin/bmcrotate/bmcrotation/").content.decode()
        self.assertIn("c01", page)
        self.assertNotIn("new-secret", page)
        self.assertNotIn("secret1", page)
