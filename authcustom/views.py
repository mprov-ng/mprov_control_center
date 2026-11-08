""" /tokens/ (#502): a user's own API tokens, for mash's `connect … --save-token`. """
from rest_framework import status
from rest_framework.authentication import BasicAuthentication, SessionAuthentication
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response
from rest_framework.views import APIView

from authcustom.authentication import UserTokenAuthentication
from authcustom.models import UserToken


def describe(token):
    return {"name": token.name, "prefix": token.prefix, "created": token.created,
            "expires": token.expiry_date, "last_used": token.last_used, "revoked": token.revoked}


class TokensAPIView(APIView):
    """
    # Your API tokens

    - `GET /tokens/`: your tokens (never their secrets).
    - `POST /tokens/ {"name": "...", "days": 365}`: a new token, returned once
      as `token`.  Needs your password (Basic) or a login, not another token.
      `days` is optional; without it the token doesn't expire.
    - `DELETE /tokens/<prefix>/`: revoke one of yours.

    Use a token as `Authorization: Token <token>`.  It acts as you, with your
    permissions.  Tokens are for staff users.
    """
    authentication_classes = [BasicAuthentication, SessionAuthentication, UserTokenAuthentication]
    # tokens are for staff users (#502)
    permission_classes = [IsAdminUser]

    def get(self, request, prefix=None):
        tokens = UserToken.objects.filter(user=request.user)
        return Response([describe(t) for t in tokens])

    def post(self, request, prefix=None):
        if isinstance(request.auth, UserToken) or prefix is not None:
            return Response({"detail": "Make a token with your password or a login, not with a token."},
                            status=status.HTTP_403_FORBIDDEN)
        data = request.data if isinstance(request.data, dict) else {}
        name, days = data.get("name"), data.get("days")
        errors = {}
        if not (isinstance(name, str) and 0 < len(name.strip()) <= 50):
            errors["name"] = "Must be a non-blank string of up to 50 characters."
        if days is not None and not (isinstance(days, int) and not isinstance(days, bool) and 0 < days <= 3650):
            errors["days"] = "Must be a whole number of days from 1 to 3650, or left out."
        if errors:
            return Response(errors, status=status.HTTP_400_BAD_REQUEST)
        token, secret = UserToken.make(request.user, name.strip(), days)
        return Response({"token": secret, **describe(token)}, status=status.HTTP_201_CREATED)

    def delete(self, request, prefix=None):
        token = UserToken.objects.filter(user=request.user, prefix=prefix).first() if prefix else None
        if token is None:
            return Response({"detail": "No such token of yours."}, status=status.HTTP_404_NOT_FOUND)
        token.revoked = True
        token.save(update_fields=["revoked"])
        return Response(status=status.HTTP_204_NO_CONTENT)
