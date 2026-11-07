from django.contrib import admin, messages
from django.utils import timezone

from pki.models import AgentCredential


@admin.register(AgentCredential)
class AgentCredentialAdmin(admin.ModelAdmin):
    """ The client certificates issued to job servers and systems (#381).
    They're issued by enrollment, never here; revoke one to cut that agent off. """
    list_display = ('user', 'kind', 'jobserver', 'system', 'not_after', 'last_seen', 'revoked_at', 'is_active')
    list_filter = ('kind', ('revoked_at', admin.EmptyFieldListFilter))
    search_fields = ('user__username', 'fingerprint', 'serial', 'jobserver__name', 'system__hostname')
    fields = ('kind', 'jobserver', 'system', 'user', 'serial', 'fingerprint', 'not_before', 'not_after',
              'created', 'last_seen', 'revoked_at', 'certificate')
    readonly_fields = fields
    actions = ['revoke']

    def has_add_permission(self, request):
        return False

    @admin.action(description="Revoke selected credentials", permissions=["change"])
    def revoke(self, request, queryset):
        count = queryset.filter(revoked_at__isnull=True).update(revoked_at=timezone.now())
        self.message_user(request, f"Revoked {count} credential{'' if count == 1 else 's'}.", messages.SUCCESS)
