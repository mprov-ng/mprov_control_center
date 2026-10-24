from unittest import mock

from rest_framework import serializers
from rest_framework.response import Response
from rest_framework_api_key.models import APIKey

from common.serializers import NestedPrimaryKeyRelatedField
from common.testing import APITestCase
from common.views import MProvView
from jobqueue.models import Job, JobModule, JobStatus, queue_job
from scripts.models import ScriptType


class FilterByQueryParamsTests(APITestCase):
  """ MProvView filters lists by ?FIELD=VALUE through filter_by_query_params(). """

  def setUp(self):
    super().setUp()
    JobModule.objects.create(slug="pxe-update", name="PXE Update")
    JobModule.objects.create(slug="nads", name="NADS")

  def test_field_filter(self):
    response = self.get_json("/jobmodules/?name=NADS")
    self.assertEqual(response.status_code, 200)
    self.assertEqual([m["slug"] for m in response.json()], ["nads"])

  def test_no_match_is_404(self):
    self.assertEqual(self.get_json("/jobmodules/?name=nope").status_code, 404)

  def test_unknown_params_are_ignored(self):
    self.assertEqual(len(self.get_json("/jobmodules/?nope=1").json()), 2)


class UnpackedArgsTests(APITestCase):
  """ MProvView.patch() and delete() pass the URL kwargs to the DRF mixins unpacked (#259). """

  def setUp(self):
    super().setUp()
    JobModule.objects.create(slug="nads", name="NADS")

  def test_patch_passes_pk(self):
    with mock.patch.object(MProvView, "partial_update", return_value=Response()) as partial_update:
      self.client.patch("/jobmodules/nads/", {"name": "x"}, content_type="application/json")
    self.assertEqual(partial_update.call_args.kwargs, {"pk": "nads"})

  def test_delete_passes_pk(self):
    with mock.patch.object(MProvView, "destroy", return_value=Response(status=204)) as destroy:
      self.client.delete("/jobmodules/nads/", content_type="application/json")
    self.assertEqual(destroy.call_args.kwargs, {"pk": "nads"})


class QueueJobTests(APITestCase):
  """ queue_job() reuses a pending job with the same module and params. """

  def setUp(self):
    super().setUp()
    self.module = JobModule.objects.create(slug="repo-update", name="Update Repos")
    JobStatus.objects.create(pk=1, name="PENDING")
    JobStatus.objects.create(pk=2, name="RUNNING")

  def test_pending_job_is_reused(self):
    first = queue_job(self.module, {"repo_id": 1})
    self.assertEqual(queue_job(self.module, {"repo_id": 1}), first)
    self.assertEqual(Job.objects.count(), 1)
    self.assertEqual((first.name, first.status_id), ("Update Repos", 1))

  def test_different_params_or_running_job_get_a_new_one(self):
    first = queue_job(self.module, {"repo_id": 1})
    queue_job(self.module, {"repo_id": 2})
    Job.objects.filter(pk=first.pk).update(status=2)
    queue_job(self.module, {"repo_id": 1})
    self.assertEqual(Job.objects.count(), 3)


class ScriptTypeSerializer(serializers.ModelSerializer):
  class Meta:
    model = ScriptType
    fields = '__all__'


class AnonymousPatchTests(APITestCase):
  """ MProvView.patch() rejects anonymous callers instead of substituting admin (#331). """

  def setUp(self):
    super().setUp()
    JobModule.objects.create(slug="nads", name="NADS")
    _, self.key = APIKey.objects.create_key(name="test-331")

  def test_api_key_patch_is_rejected_not_run_as_admin(self):
    # A valid API key passes the HasAPIKey|IsAuthenticated gate but leaves
    # request.user anonymous; the PATCH must be rejected, not silently
    # executed as the hard-coded admin superuser.
    anon = self.client_class()  # fresh client: no login session
    response = anon.patch(
        "/jobmodules/nads/", {"name": "hijacked"},
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Api-Key {self.key}")
    self.assertEqual(response.status_code, 403)
    self.assertEqual(JobModule.objects.get(slug="nads").name, "NADS")

  def test_authenticated_patch_still_works(self):
    response = self.client.patch("/jobmodules/nads/", {"name": "Renamed"},
                                 content_type="application/json")
    self.assertEqual(response.status_code, 200)
    self.assertEqual(JobModule.objects.get(slug="nads").name, "Renamed")


class NestedPrimaryKeyRelatedFieldTests(APITestCase):
  """ NestedPrimaryKeyRelatedField takes a primary key and renders the nested object. """

  def test_write_pk_read_nested(self):
    script_type = ScriptType.objects.create(name="Post Boot", slug="post-boot")
    field = NestedPrimaryKeyRelatedField(ScriptTypeSerializer, queryset=ScriptType.objects.all())
    self.assertEqual(field.to_internal_value("post-boot"), script_type)
    self.assertEqual(field.to_representation(script_type), {"name": "Post Boot", "slug": "post-boot"})
