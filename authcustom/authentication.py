""" `Authorization: Token <token>` (#502): a person's API token. """
from rest_framework import exceptions
from rest_framework.authentication import BaseAuthentication, get_authorization_header


class UserTokenAuthentication(BaseAuthentication):
    """ Authenticates as the token's user.  A missing, unknown, revoked or
    expired token, or an inactive user, gets a 401 that says which. """
    keyword = b"token"

    def authenticate(self, request):
        from authcustom.models import UserToken
        auth = get_authorization_header(request).split()
        if not auth or auth[0].lower() != self.keyword:
            return None
        if len(auth) != 2:
            raise exceptions.AuthenticationFailed("Send the token as \"Authorization: Token <token>\".")
        try:
            key = auth[1].decode()
        except UnicodeError:
            raise exceptions.AuthenticationFailed("Unknown token.")
        prefix = key.partition(".")[0]
        token = UserToken.objects.select_related("user").filter(prefix=prefix).first()
        if token is None or not token.is_valid(key):
            raise exceptions.AuthenticationFailed("Unknown token.")
        if token.revoked:
            raise exceptions.AuthenticationFailed("This token was revoked.")
        if token.has_expired:
            raise exceptions.AuthenticationFailed(f"This token expired on {token.expiry_date:%Y-%m-%d}.")
        if not token.user.is_active:
            raise exceptions.AuthenticationFailed("This token's user is inactive.")
        if not token.user.is_staff:
            # tokens are for staff users (#502)
            raise exceptions.AuthenticationFailed("This token's user isn't staff any more.")
        if token.user.is_superuser and token.made_for_someone_else:
            # someone else saw its secret, and tokens are never made for a
            # superuser by someone else; its user was promoted since (#561)
            raise exceptions.AuthenticationFailed(
                "This token's user is a superuser now, and the token was made by someone else.")
        token.touch()
        return token.user, token

    def authenticate_header(self, request):
        return 'Token realm="mprov"'
