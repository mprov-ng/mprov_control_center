"""
The API version lock (#452).  Every reply carries the mPCC's API version
(the major.minor of mprov_control_center.version) in the mProv-Version
header.  A request made with the API key, which is how job servers, mash
and node scripts authenticate, must send the same major.minor in that
header, or it gets 426 Upgrade Required.

Browser sessions (the admin, the API's docs pages) and unauthenticated
requests (image, repo and iPXE serves, node registration, the health check)
aren't checked.  Node scripts baked into images can't be rebuilt with every
mPCC release, so the endpoints in settings.MPROV_VERSION_EXEMPT pass for a
request that comes from one of a known system's network interface
addresses, with a warning logged every time.  MPROV_SKIP_VERSION_CHECK
turns the check off for development and CI.
"""
import functools
import logging
import re

from django.conf import settings
from django.core.exceptions import ValidationError
from django.http import JsonResponse

from mprov_control_center.version import API_VERSION

log = logging.getLogger("mprov.version")

HEADER = "mProv-Version"


def major_minor(value):
    """ The major.minor of a version such as "0.6" or "0.6.2", or None. """
    if not isinstance(value, str):
        return None
    parts = value.strip().split(".")
    if len(parts) < 2 or not all(part.isdigit() for part in parts[:2]):
        return None
    return f"{int(parts[0])}.{int(parts[1])}"


@functools.lru_cache(maxsize=None)
def exemptions(entries):
    """
    The compiled exemption list: (path regex, required query key or None)
    for each entry, such as "systems/?self" or "networks/<pk>/".  "<pk>" is
    any one path segment, and "/" is the API index.
    """
    result = []
    for entry in entries:
        path, _, key = entry.partition("?")
        parts = [part for part in path.strip().split("/") if part]
        pattern = "".join("/" + ("[^/]+" if part == "<pk>" else re.escape(part)) for part in parts)
        result.append((re.compile("^" + pattern + "/$"), key.strip() or None))
    return tuple(result)


class APIVersionMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
        if settings.MPROV_SKIP_VERSION_CHECK:
            log.warning("MPROV_SKIP_VERSION_CHECK is set: API clients' versions aren't checked. "
                        "Never set it in production.")

    def __call__(self, request):
        response = self.check(request)
        if response is None:
            response = self.get_response(request)
        response[HEADER] = API_VERSION
        return response

    def check(self, request):
        """ The 426 reply for an API-key request with the wrong version, or None. """
        if settings.MPROV_SKIP_VERSION_CHECK:
            return None
        if not request.META.get("HTTP_AUTHORIZATION", "").startswith("Api-Key "):
            return None
        sent = request.headers.get(HEADER)
        if major_minor(sent) == API_VERSION:
            return None
        if self.exempt(request):
            log.warning(f"{request.method} {request.get_full_path()} from {self.client_ip(request)}: "
                        f"mProv version {sent or 'not sent'}, not {API_VERSION}; let through by MPROV_VERSION_EXEMPT.")
            return None
        got = "no version" if sent is None else sent
        return JsonResponse({"detail": f"mProv version mismatch: this mPCC speaks {API_VERSION}, the client sent {got}. "
                                       f"Upgrade the client, or the mPCC, so both are {API_VERSION}.",
                             "expected": API_VERSION, "got": sent}, status=426)

    @staticmethod
    def client_ip(request):
        from systems.views_noauth import get_client_ip
        return get_client_ip(request)

    def exempt(self, request):
        """ An exempted endpoint, requested from a known system's address. """
        for pattern, key in exemptions(tuple(settings.MPROV_VERSION_EXEMPT)):
            if pattern.match(request.path) and (key is None or key in request.GET):
                return self.from_a_system(request)
        return False

    def from_a_system(self, request):
        from systems.models import NetworkInterface
        try:
            return NetworkInterface.objects.filter(ipaddress=self.client_ip(request)).exists()
        except (TypeError, ValueError, ValidationError):
            return False
