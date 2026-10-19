from django.test import TestCase


class DataModelViewTests(TestCase):
  """ /datamodel/ describes the fields of a model. """

  def test_unknown_model_is_404(self):
    response = self.client.get("/datamodel/", {"model": "nope.models.Nope"})
    self.assertEqual(response.status_code, 404)
    self.assertEqual(response.json(), {"error": "Unknown Model Requested"})
