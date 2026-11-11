""" Per-user API tokens (#502): how mash and people's scripts use the API
without the shared key or a password on every request. """
import datetime

from django.conf import settings
from django.db import models
from django.utils import timezone
from rest_framework_api_key.models import AbstractAPIKey


class UserToken(AbstractAPIKey):
    """ An API token that acts as its user: stored hashed, shown once when
    it's made, revocable, optionally expiring.  A user may hold several, one
    per machine or script. """
    # how often last_used is written, at most
    TOUCH_EVERY = datetime.timedelta(minutes=1)

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="api_tokens")
    last_used = models.DateTimeField(null=True, blank=True, editable=False, verbose_name="Last Used")
    # who was shown the secret (#561): the user themselves, someone with
    # add_usertoken who made it for them in the admin, or empty for a token
    # made with manage.py mprov_token or before this field existed
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                   editable=False, related_name="+", verbose_name="Made By")

    class Meta(AbstractAPIKey.Meta):
        verbose_name = "API Token"
        verbose_name_plural = "API Tokens"

    def __str__(self):
        return f"{self.name} ({self.prefix}…, {self.user.username})"

    @classmethod
    def make(cls, user, name, days=None, created_by=None):
        """ (token, the secret to give the user once).  created_by is who
        sees the secret, when that's a logged-in person. """
        expiry = timezone.now() + datetime.timedelta(days=days) if days else None
        return cls.objects.create_key(user=user, name=name, expiry_date=expiry, created_by=created_by)

    @property
    def made_for_someone_else(self):
        """ Made in the admin by someone other than its user (#561). """
        return self.created_by_id is not None and self.created_by_id != self.user_id

    def touch(self):
        """ Record a use, at most once every TOUCH_EVERY. """
        now = timezone.now()
        if self.last_used is None or now - self.last_used >= self.TOUCH_EVERY:
            type(self).objects.filter(pk=self.pk).update(last_used=now)
            self.last_used = now
