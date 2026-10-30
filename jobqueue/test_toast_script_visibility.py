from django.test import TestCase


class ToastScriptVisibilityTests(TestCase):
  """ job_notifications.js only loads for a logged-in staff user, never on the login page. """

  def test_toast_script_not_on_login_page(self):
    response = self.client.get("/admin/login/")
    self.assertNotContains(response, "job_notifications.js")

  def test_toast_script_on_admin_page_for_staff_user(self):
    from django.contrib.auth.models import User
    User.objects.create_superuser("admin", "admin@example.com", "password")
    self.client.login(username="admin", password="password")
    response = self.client.get("/admin/")
    self.assertContains(response, "job_notifications.js")
