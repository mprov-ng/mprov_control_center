from django.test import TestCase


class DataModelViewTests(TestCase):
  """ /datamodel/ describes the fields of a model. """

  def test_field_type_key(self):
    response = self.client.get("/datamodel/", {"model": "jobqueue.models.JobModule"})
    self.assertEqual(response.status_code, 200)
    self.assertEqual(response.json()["fields"]["name"], {"type": "string", "required": True})

  def required(self, model):
    response = self.client.get("/datamodel/", {"model": model})
    self.assertEqual(response.status_code, 200)
    return {name: f["required"] for name, f in response.json()["fields"].items()}

  def test_fields_with_a_default_are_not_required(self):
    # mprov-ng/mash#8: mash refused to create a System without these.
    self.assertFalse(self.required("systems.models.System")["timestamp"])
    self.assertFalse(self.required("systems.models.NetworkInterface")["isgateway"])
    self.assertFalse(self.required("systems.models.SystemBMC")["vlan"])

  def test_fields_the_server_sets_are_not_required(self):
    # editable=False: a pre_save signal makes SystemImage's slug from its name.
    self.assertFalse(self.required("systems.models.SystemImage")["slug"])

  def test_fields_without_a_default_are_still_required(self):
    self.assertTrue(self.required("systems.models.System")["hostname"])
    self.assertFalse(self.required("systems.models.NetworkInterface")["hostname"])
