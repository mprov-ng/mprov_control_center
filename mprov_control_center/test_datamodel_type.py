from django.test import TestCase


class DataModelViewTests(TestCase):
  """ /datamodel/ describes the fields of a model. """

  def test_field_type_key(self):
    response = self.client.get("/datamodel/", {"model": "jobqueue.models.JobModule"})
    self.assertEqual(response.status_code, 200)
    self.assertEqual(response.json()["fields"]["name"], {"type": "string", "required": True})
