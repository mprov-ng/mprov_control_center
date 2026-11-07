""" Who may use the API (#272, #381).

- An agent with a client certificate (pki.authentication) gets only what its
  kind needs (pki.rules): a system acts on itself, a job server reads the
  inventory and writes its own state.
- The shared API key, which every client used before #381, is governed by
  MPROV_SHARED_KEY_MODE:
    all   - accepted everywhere, as before, with a warning at start.
    nodes - accepted only on what a system may do, for the system the
            caller's address belongs to.  For old node images until they're
            rebuilt.
    off   - refused.
- A logged-in user (session, Basic) may use the whole API, as before.
"""
import logging

from django.conf import settings
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import BasePermission
from rest_framework_api_key.permissions import HasAPIKey

log = logging.getLogger("mprov.auth")

SHARED_KEY_MODES = ("all", "nodes", "off")


def shared_key_mode():
    mode = getattr(settings, "MPROV_SHARED_KEY_MODE", "all")
    return mode if mode in SHARED_KEY_MODES else "off"


def system_from_address(request):
    """ The system whose network interface has the caller's address, or None. """
    from django.core.exceptions import ValidationError
    from systems.models import NetworkInterface
    from systems.views_noauth import get_client_ip
    try:
        nic = NetworkInterface.objects.select_related("system").filter(ipaddress=get_client_ip(request)).first()
    except (TypeError, ValueError, ValidationError):
        return None
    return nic.system if nic else None


_warned = set()


def warn_once(key, message):
    if key not in _warned:
        _warned.add(key)
        log.warning(message)


class MProvPermission(BasePermission):
    message = "Not allowed."

    def has_permission(self, request, view):
        from pki import rules
        from pki.models import AgentCredential
        credential = request.auth if isinstance(request.auth, AgentCredential) else None
        if credential is not None:
            if credential.kind == AgentCredential.SYSTEM:
                allowed = rules.system_allows(credential.system, request)
            elif credential.kind == AgentCredential.BUILD:
                allowed = rules.build_allows(credential.image, request)
            else:
                allowed = rules.jobserver_allows(credential.jobserver, request)
            if not allowed:
                log.warning(f"refused {request.method} {request.get_full_path()} for {credential.user.username}")
                self.message = f"{credential.user.username} may not {request.method} this."
            return allowed
        if request.user and request.user.is_authenticated:
            return True
        if HasAPIKey().has_permission(request, view):
            return self.shared_key(request)
        return False

    def shared_key(self, request):
        mode = shared_key_mode()
        if mode == "all":
            return True
        if mode == "nodes":
            from pki import rules
            system = system_from_address(request)
            if system is not None and rules.system_allows(system, request):
                warn_once(("node", system.pk), f"{system.hostname} uses the shared API key; rebuild its image "
                                               "so it uses its own credential (#381).")
                return True
        log.warning(f"refused the shared API key for {request.method} {request.get_full_path()} "
                    f"(MPROV_SHARED_KEY_MODE={mode})")
        # 403 with the reason: returning False would be DRF's bare 401
        # "credentials not provided", as the key isn't a DRF authenticator.
        raise PermissionDenied("The shared API key isn't accepted here (MPROV_SHARED_KEY_MODE="
                               f"{mode}). Use this agent's own credential.")

