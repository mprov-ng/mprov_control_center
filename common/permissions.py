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
- A person (a login, Basic, or one of their API tokens, #502) gets their own
  Django model permissions: GET needs view_<model>, POST add_, PATCH/PUT
  change_, DELETE delete_ on the view's model.  A view whose request does
  more than that declares what it needs in `mprov_permissions`.  A view with
  no model and no declaration is for superusers only.  Superusers may do
  everything.
"""
import logging

from django.conf import settings
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import BasePermission
from rest_framework_api_key.permissions import HasAPIKey

log = logging.getLogger("mprov.auth")

SHARED_KEY_MODES = ("all", "nodes", "off")


def shared_key_mode():
    """ MPROV_SHARED_KEY_MODE, or "off" if it isn't one of the known modes. """
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

ACTIONS = {"GET": "view", "HEAD": "view", "OPTIONS": "view", "POST": "add", "PUT": "change",
           "PATCH": "change", "DELETE": "delete"}


def required_permissions(request, view):
    """ The Django permissions a person needs for this request, or None when
    the view doesn't say (superusers only).

    A view may set `mprov_permissions` to {method: [perm, ...]}, or to a
    function (request) -> [perm, ...]; otherwise it's the method's action
    on the view's model. """
    declared = getattr(view, "mprov_permissions", None)
    if callable(declared):
        perms = declared(request)
        return list(perms) if perms is not None else None
    if declared is not None:
        perms = declared.get(request.method)
        return list(perms) if perms is not None else None
    model = getattr(view, "model", None) or getattr(getattr(view, "queryset", None), "model", None)
    action = ACTIONS.get(request.method)
    if model is None or action is None:
        return None
    return [f"{model._meta.app_label}.{action}_{model._meta.model_name}"]


def warn_once(key, message):
    """ Log message as a warning the first time key is seen in this process. """
    if key not in _warned:
        _warned.add(key)
        log.warning(message)


class MProvPermission(BasePermission):
    """ The project's default permission: an agent certificate gets what its kind
    may do, a person their Django model permissions, and the shared API key
    what MPROV_SHARED_KEY_MODE allows. """
    message = "Not allowed."

    def has_permission(self, request, view):
        """ Check the request's certificate, then its user, then the shared key. """
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
            return self.person(request, view)
        if HasAPIKey().has_permission(request, view):
            return self.shared_key(request)
        return False

    def person(self, request, view):
        """ Whether a person may make this request: a superuser always, anyone
        else with the Django permissions it needs (required_permissions). """
        user = request.user
        if user.is_superuser:
            return True
        perms = required_permissions(request, view)
        if perms is None:
            self.message = "Only a superuser may do this."
        elif user.has_perms(perms):
            return True
        else:
            missing = [perm for perm in perms if not user.has_perm(perm)]
            self.message = f"{user.username} needs the permission {', '.join(missing)}."
        log.info(f"refused {request.method} {request.get_full_path()} for {user.username}: {self.message}")
        return False

    def shared_key(self, request):
        """ Whether the shared API key may make this request in the current mode;
        refused with a 403 that says why. """
        mode = shared_key_mode()
        if mode == "all":
            return True
        if mode == "nodes":
            from pki import rules
            system = system_from_address(request)
            if system is not None and rules.system_allows(system, request):
                warn_once(("node", system.pk), f"{system.hostname} uses the shared API key; rebuild its image "
                                               "so it uses its own credential.")
                return True
        log.warning(f"refused the shared API key for {request.method} {request.get_full_path()} "
                    f"(MPROV_SHARED_KEY_MODE={mode})")
        # 403 with the reason: returning False would be DRF's bare 401
        # "credentials not provided", as the key isn't a DRF authenticator.
        raise PermissionDenied("The shared API key isn't accepted here (MPROV_SHARED_KEY_MODE="
                               f"{mode}). Use this agent's own credential.")

