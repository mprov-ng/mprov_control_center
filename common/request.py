import threading

_thread_locals = threading.local()


def get_current_request():
    return getattr(_thread_locals, "request", None)


class CurrentRequestMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        _thread_locals.request = request
        try:
            return self.get_response(request)
        finally:
            if hasattr(_thread_locals, "request"):
                del _thread_locals.request


SHARED_KEY_USER = "mprov.shared-key"
NADS_USER = "mprov.nads"


def service_user(username, first_name):
    """ A service user that writes are attributed to (#5): made the first
    time, with no usable password, never staff. """
    from django.contrib.auth import get_user_model
    user, created = get_user_model().objects.get_or_create(username=username, defaults={
        "first_name": first_name, "is_staff": False, "is_superuser": False})
    if created:
        user.set_unusable_password()
        user.save(update_fields=["password"])
    return user


def shared_key_user():
    """ The shared API key's writes; it goes with the key in 0.8.0. """
    return service_user(SHARED_KEY_USER, "Shared API key")


def nads_user():
    """ N.A.D.S. registration's writes (/systems/register, unauthenticated). """
    return service_user(NADS_USER, "N.A.D.S. registration")


def acting_user(request):
    """ Who a save made during this request is attributed to (#327, #331,
    #381, #5): the request's user, which for an agent with a client
    certificate is its own service user, and for a person is them.  A
    request with the shared API key and no user is mprov.shared-key, and
    N.A.D.S. registration is mprov.nads.  Any other unauthenticated request
    falls back to the first superuser, as before. """
    from django.contrib.auth import get_user_model
    user = getattr(request, "user", None)
    if user is not None and user.is_authenticated:
        return user
    meta = getattr(request, "META", {})
    if meta.get("HTTP_AUTHORIZATION", "").split(" ", 1)[0].lower() == "api-key":
        return shared_key_user()
    if getattr(request, "path", "").rstrip("/") == "/systems/register":
        return nads_user()
    return get_user_model().objects.filter(is_superuser=True).order_by("pk").first()


def stamp_users(instance):
    """ For a save made during a request: record the acting user as
    instance.updated_by, and as instance.created_by too if the object is new
    (#493).  Before, created_by was overwritten on every save, so it named
    whoever saved last.  Saves outside a request (jobs, management commands)
    change neither. """
    request = get_current_request()
    if request is None:
        return
    user = acting_user(request)
    if instance._state.adding:
        instance.created_by = user
    instance.updated_by = user
