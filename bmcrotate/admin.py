""" The "BMC Credential Changes" report (#486): every change or check made on
the BMCs, what each one stored, and "Find which credentials work" for one
the mPCC couldn't confirm. """
from django.contrib import admin, messages
from django.utils.html import format_html

from bmcrotate import logic
from bmcrotate.models import BMCRotation


@admin.register(BMCRotation)
class BMCRotationAdmin(admin.ModelAdmin):
  list_display = ('system', 'kind', 'outcome', 'method', 'tls', 'stored', 'error', 'requested_by', 'created', 'finished')
  list_filter = ('status', 'kind')
  search_fields = ('bmc__system__hostname', 'bmc__ipaddress')
  actions = ['find']
  # the credentials are never shown
  fields = ('system', 'kind', 'status', 'method', 'tls_verified', 'stored', 'error', 'requested_by', 'created', 'finished', 'job')
  readonly_fields = fields

  def has_add_permission(self, request):
    return False

  def has_change_permission(self, request, obj=None):
    return False

  def get_actions(self, request):
    actions = super().get_actions(request)
    if not request.user.has_perm('systems.change_systembmc'):
      actions.pop('find', None)
    return actions

  @admin.display(description="System", ordering='bmc__system__hostname')
  def system(self, obj):
    return obj.bmc.system.hostname

  @admin.display(description="Status", ordering='status')
  def outcome(self, obj):
    colour = {BMCRotation.SUCCEEDED: "success", BMCRotation.PARTIAL: "warning", BMCRotation.UNCONFIRMED: "warning",
              BMCRotation.FAILED: "danger", BMCRotation.UNREACHABLE: "danger"}.get(obj.status, "secondary")
    return format_html('<span class="badge bg-{}">{}</span>', colour, obj.get_status_display())

  @admin.display(description="TLS")
  def tls(self, obj):
    if obj.tls_verified is False:
      return format_html('<span class="badge bg-warning" title="{}">not verified</span>',
                         "The BMC's HTTPS certificate wasn't verified (verifyBMC is off on the job server).")
    return "verified" if obj.tls_verified else "-"

  @admin.action(description="Find which credentials work (for unconfirmed changes)")
  def find(self, request, queryset):
    queued = [r for r in queryset.select_related('bmc__system') if logic.find(r, request.user)]
    others = queryset.count() - len(queued)
    self.message_user(request, f"Queued a search on {len(queued)} BMCs: each tries the old credentials, the new "
                               "password, then the new user and password, and stores the first that works.")
    if others:
      self.message_user(request, f"Skipped {others} that aren't unconfirmed.", level=messages.WARNING)
