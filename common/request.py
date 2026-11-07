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


def acting_user(request):
    """ Who a save made during this request is attributed to (#327, #331,
    #381): the request's user, which for an agent with a client certificate
    is its own service user.  Only a request with no user (the shared API key,
    or an unauthenticated endpoint such as N.A.D.S. registration) falls back to
    the first superuser, as before. """
    from django.contrib.auth import get_user_model
    user = getattr(request, "user", None)
    if user is not None and user.is_authenticated:
        return user
    return get_user_model().objects.filter(is_superuser=True).order_by("pk").first()
