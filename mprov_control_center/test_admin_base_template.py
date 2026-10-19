from django.test import TestCase


class AdminBaseTemplateTests(TestCase):
  """ templates/admin/base.html adds mProv's admin JS and CSS to every admin page. """

  def test_kept_when_a_child_overrides_extrahead(self):
    from django.contrib.auth.models import User
    from django.template import engines
    from django.test import RequestFactory
    request = RequestFactory().get("/admin/")
    request.user = User.objects.create_superuser("admin", "admin@example.com", "password")
    template = engines["django"].from_string(
      '{% extends "admin/base.html" %}{% block extrahead %}<meta name="child">{% endblock %}')
    html = template.render({}, request)
    self.assertIn('<meta name="child">', html)
    self.assertIn("admin/js/job_notifications.js", html)
    self.assertIn("/static/css/mprov.css", html)
