""" The API Keys admin, marked as legacy (#500).

From 0.7.0 job servers and nodes use their own credentials (pki); the shared
API key works only while MPROV_SHARED_KEY_MODE is all or nodes, and is
removed in 0.8.0.  The pages say so; adding a key still works, so a site on
"all" can rotate it. """
from django.contrib import admin, messages
from rest_framework_api_key import admin as api_key_admin  # registers APIKey first
from rest_framework_api_key.models import APIKey

from common.permissions import shared_key_mode

NOW = {
  "all": "now: all, accepted everywhere",
  "nodes": "now: nodes, accepted only for what a node does to itself",
}


def legacy_banner():
  """ The warning for the current MPROV_SHARED_KEY_MODE. """
  mode = shared_key_mode()
  if mode == "off":
    return "API keys are not accepted (MPROV_SHARED_KEY_MODE=off) and are removed in 0.8.0."
  return ("Legacy: API keys are deprecated. They work only while MPROV_SHARED_KEY_MODE is all or nodes "
          f"({NOW[mode]}) and are removed in 0.8.0. Job servers and nodes now use their own credentials "
          "(Agent Identities).")


class LegacyAPIKeyAdmin(api_key_admin.APIKeyModelAdmin):
  def warn(self, request):
    # on GET only: after a POST the page redirects, and the next GET warns.
    if request.method == "GET":
      messages.warning(request, legacy_banner())

  def changelist_view(self, request, extra_context=None):
    self.warn(request)
    return super().changelist_view(request, extra_context)

  def changeform_view(self, request, object_id=None, form_url="", extra_context=None):
    self.warn(request)
    return super().changeform_view(request, object_id, form_url, extra_context)


admin.site.unregister(APIKey)
admin.site.register(APIKey, LegacyAPIKeyAdmin)
