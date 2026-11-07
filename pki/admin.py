import datetime

from django import forms
from django.contrib import admin, messages
from django.utils import timezone
from django.utils.html import escape, mark_safe

from pki.models import AgentCredential, EnrollmentToken


def ca_fingerprint():
    from pki.authentication import ca_cert
    from pki.ca import fingerprint
    ca = ca_cert()
    return fingerprint(ca) if ca is not None else "(no CA yet)"


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


class EnrollmentTokenForm(forms.ModelForm):
    hours = forms.IntegerField(min_value=1, max_value=24 * 30, initial=24,
                               help_text="How long it can be used for. It's single-use either way.")

    class Meta:
        model = EnrollmentToken
        fields = ('note',)


@admin.register(EnrollmentToken)
class EnrollmentTokenAdmin(admin.ModelAdmin):
    """ One-time tokens job servers enroll with (#381).  Add one, give it to
    the job server, and it's shown only once. """
    form = EnrollmentTokenForm
    list_display = ('prefix', 'note', 'created', 'created_by', 'expires', 'used_at', 'jobserver', 'usable')
    readonly_fields = ('prefix', 'created', 'created_by', 'expires', 'used_at', 'jobserver')

    def get_fields(self, request, obj=None):
        return ('note', 'hours') if obj is None else ('prefix', 'note', 'created', 'created_by', 'expires',
                                                      'used_at', 'jobserver')

    def get_form(self, request, obj=None, **kwargs):
        if obj is not None:
            kwargs['form'] = forms.ModelForm
        return super().get_form(request, obj, **kwargs)

    def save_model(self, request, obj, form, change):
        if change:
            return super().save_model(request, obj, form, change)
        row, secret = EnrollmentToken.make(datetime.timedelta(hours=form.cleaned_data['hours']),
                                           note=form.cleaned_data.get('note', ''), user=request.user)
        obj.pk = row.pk
        obj.refresh_from_db()
        self.message_user(request, mark_safe(
            f"Enrollment token, shown only this once: <code>{escape(secret)}</code><br>"
            f"Give it to the job server to enroll with. CA fingerprint to check: "
            f"<code>{escape(ca_fingerprint())}</code>"), messages.WARNING)
