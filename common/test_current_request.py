from unittest import mock
import threading

from django.test import SimpleTestCase, RequestFactory
from django.contrib.auth.models import AnonymousUser

from common.request import CurrentRequestMiddleware, get_current_request


class CurrentRequestMiddlewareTests(SimpleTestCase):
    """Items 1-4,9 from comment 6530426203; no DB."""

    def test_get_current_request_during_and_after_get_response(self):
        """Item 1: returns request inside get_response, None after."""
        factory = RequestFactory()
        request = factory.get("/")
        seen_inside = []

        def get_response(req):
            seen_inside.append(get_current_request())
            return "ok"

        mw = CurrentRequestMiddleware(get_response)
        result = mw(request)
        self.assertEqual(result, "ok")
        self.assertIs(seen_inside[0], request)
        self.assertIsNone(get_current_request())

    def test_cleared_when_view_raises(self):
        """Item 2: finally path clears even when get_response raises."""
        from django.test import RequestFactory
        factory = RequestFactory()
        request = factory.get("/")

        def raising_get_response(req):
            assert get_current_request() is req
            raise ValueError("boom")

        mw = CurrentRequestMiddleware(raising_get_response)
        with self.assertRaises(ValueError):
            mw(request)
        self.assertIsNone(get_current_request(), "stale request must not survive a raised view (mod_wsgi thread reuse)")

    def test_thread_isolation(self):
        """Item 3: request set in one thread not visible from another."""
        factory = RequestFactory()
        request = factory.get("/")

        seen_in_other = []

        def get_response(req):
            # While the main thread holds the request, spawn another thread.
            def other():
                seen_in_other.append(get_current_request())
            t = threading.Thread(target=other)
            t.start()
            t.join()
            return "ok"

        mw = CurrentRequestMiddleware(get_response)
        mw(request)
        self.assertEqual(seen_in_other, [None])
        self.assertIsNone(get_current_request())

    def test_none_outside_request(self):
        """Item 4: None outside any request (plain ORM/management command path)."""
        self.assertIsNone(get_current_request())

    def test_no_inspect_stack_in_models(self):
        """Item 9: regression guard - no inspect.stack left in signal modules."""
        import pathlib
        from django.conf import settings
        base = pathlib.Path(settings.BASE_DIR)
        for rel in ("systems/models.py", "networks/models.py"):
            text = (base / rel).read_text()
            self.assertNotIn("inspect.stack", text, f"{rel} must not contain inspect.stack (replaced by current-request middleware)")

    def test_inspect_stack_patched_still_works(self):
        """Item 9 alternative: even if inspect.stack raises, a request-bound save still sets created_by."""
        # This only checks the middleware path doesn't call inspect.stack;
        # the full save-through-request is covered in created_by tests.
        # Here we just assert the middleware/request helper itself doesn't use inspect.stack.
        factory = RequestFactory()
        request = factory.get("/")
        request.user = AnonymousUser()

        def get_response(req):
            with mock.patch("inspect.stack", side_effect=RuntimeError("should not be called")):
                # get_current_request should still work without touching inspect.stack
                self.assertIs(get_current_request(), req)
            return "ok"

        mw = CurrentRequestMiddleware(get_response)
        mw(request)
        self.assertIsNone(get_current_request())
