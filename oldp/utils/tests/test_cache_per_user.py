"""Unit tests for the cache_per_user and cache_per_role decorators.

Tests cover:
- Caching for anonymous users
- Caching for authenticated users
- POST request handling
- TTL and prefix options
- Role-based caching (anon/auth/staff)
"""

import logging
from unittest.mock import MagicMock, patch

from django.core.cache import cache
from django.http import HttpResponse
from django.template.response import TemplateResponse
from django.test import RequestFactory, TestCase, override_settings, tag

from oldp.utils.cache_per_user import cache_per_role, cache_per_user

logger = logging.getLogger(__name__)


# Use locmem cache for testing since TestConfiguration uses DummyCache
CACHES_OVERRIDE = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "unique-snowflake",
    }
}


@tag("utils", "cache")
@override_settings(CACHES=CACHES_OVERRIDE)
class CachePerUserTestCase(TestCase):
    """Tests for the cache_per_user decorator."""

    def setUp(self):
        self.factory = RequestFactory()
        cache.clear()

    def tearDown(self):
        cache.clear()

    def test_caches_anonymous_user_response(self):
        """Test that responses for anonymous users are cached."""
        call_count = {"count": 0}

        @cache_per_user(ttl=60)
        def view_func(request):
            call_count["count"] += 1
            return HttpResponse("Hello")

        request = self.factory.get("/test/")
        request.user = MagicMock()
        request.user.is_authenticated = False

        # First call
        response1 = view_func(request)
        self.assertEqual(call_count["count"], 1)

        # Second call - should use cache
        response2 = view_func(request)
        self.assertEqual(call_count["count"], 1)  # Still 1, used cache

        self.assertEqual(response1.content, response2.content)

    def test_caches_authenticated_user_separately(self):
        """Test that authenticated users have separate cache entries."""
        call_count = {"count": 0}

        @cache_per_user(ttl=60)
        def view_func(request):
            call_count["count"] += 1
            return HttpResponse(f"Hello user {request.user.id}")

        request1 = self.factory.get("/test/")
        request1.user = MagicMock()
        request1.user.is_authenticated = True
        request1.user.id = 1

        request2 = self.factory.get("/test/")
        request2.user = MagicMock()
        request2.user.is_authenticated = True
        request2.user.id = 2

        # Calls for different users should not share cache
        view_func(request1)
        self.assertEqual(call_count["count"], 1)

        view_func(request2)
        self.assertEqual(call_count["count"], 2)

    def test_anonymous_users_share_cache(self):
        """Test that all anonymous users share the same cache entry."""
        call_count = {"count": 0}

        @cache_per_user(ttl=60)
        def view_func(request):
            call_count["count"] += 1
            return HttpResponse("Anonymous content")

        request1 = self.factory.get("/test/")
        request1.user = MagicMock()
        request1.user.is_authenticated = False

        request2 = self.factory.get("/test/")
        request2.user = MagicMock()
        request2.user.is_authenticated = False

        # Both anonymous users should share cache
        view_func(request1)
        view_func(request2)
        self.assertEqual(call_count["count"], 1)

    def test_post_request_not_cached_by_default(self):
        """Test that POST requests are not cached by default."""
        call_count = {"count": 0}

        @cache_per_user(ttl=60)
        def view_func(request):
            call_count["count"] += 1
            return HttpResponse("Response")

        request = self.factory.post("/test/")
        request.user = MagicMock()
        request.user.is_authenticated = False

        view_func(request)
        view_func(request)
        self.assertEqual(call_count["count"], 2)  # Called twice, no caching

    def test_post_request_cached_when_enabled(self):
        """Test that POST requests are cached when cache_post=True."""
        call_count = {"count": 0}

        @cache_per_user(ttl=60, cache_post=True)
        def view_func(request):
            call_count["count"] += 1
            return HttpResponse("Response")

        request = self.factory.post("/test/")
        request.user = MagicMock()
        request.user.is_authenticated = False

        view_func(request)
        view_func(request)
        self.assertEqual(call_count["count"], 1)  # Only called once, cached

    def test_custom_prefix(self):
        """Test that custom prefix is used in cache key."""
        call_count = {"count": 0}

        @cache_per_user(ttl=60, prefix="my_custom_prefix")
        def view_func(request):
            call_count["count"] += 1
            return HttpResponse("Response")

        request = self.factory.get("/test/")
        request.user = MagicMock()
        request.user.is_authenticated = False

        view_func(request)

        # Check that cache key uses prefix
        cache_key = "my_custom_prefix_anonymous"
        self.assertIsNotNone(cache.get(cache_key))

    def test_different_paths_have_different_cache(self):
        """Test that different paths have different cache entries."""
        call_count = {"count": 0}

        @cache_per_user(ttl=60)
        def view_func(request):
            call_count["count"] += 1
            return HttpResponse("Response")

        request1 = self.factory.get("/path1/")
        request1.user = MagicMock()
        request1.user.is_authenticated = False

        request2 = self.factory.get("/path2/")
        request2.user = MagicMock()
        request2.user.is_authenticated = False

        view_func(request1)
        view_func(request2)
        self.assertEqual(call_count["count"], 2)  # Different paths, different cache

    def test_same_path_different_query_params(self):
        """Test that different query params create different cache entries."""
        call_count = {"count": 0}

        @cache_per_user(ttl=60)
        def view_func(request):
            call_count["count"] += 1
            return HttpResponse("Response")

        request1 = self.factory.get("/test/?page=1")
        request1.user = MagicMock()
        request1.user.is_authenticated = False

        request2 = self.factory.get("/test/?page=2")
        request2.user = MagicMock()
        request2.user.is_authenticated = False

        view_func(request1)
        view_func(request2)
        self.assertEqual(call_count["count"], 2)  # Different query params

    def test_renders_template_response(self):
        """Test that TemplateResponse is rendered before caching."""
        call_count = {"count": 0}

        @cache_per_user(ttl=60)
        def view_func(request):
            call_count["count"] += 1
            response = TemplateResponse(request, "test_template.html", {})
            return response

        request = self.factory.get("/test/")
        request.user = MagicMock()
        request.user.is_authenticated = False

        with patch.object(TemplateResponse, "render") as mock_render:
            mock_render.return_value = HttpResponse("Rendered content")
            view_func(request)
            mock_render.assert_called_once()

    def test_no_ttl_uses_default_cache_timeout(self):
        """Test that not specifying TTL uses cache default."""
        call_count = {"count": 0}

        @cache_per_user()
        def view_func(request):
            call_count["count"] += 1
            return HttpResponse("Response")

        request = self.factory.get("/test/")
        request.user = MagicMock()
        request.user.is_authenticated = False

        view_func(request)
        view_func(request)
        self.assertEqual(call_count["count"], 1)

    def test_passes_args_to_view(self):
        """Test that args and kwargs are passed to the view function."""

        @cache_per_user(ttl=60)
        def view_func(request, pk, name=None):
            return HttpResponse(f"pk={pk}, name={name}")

        request = self.factory.get("/test/")
        request.user = MagicMock()
        request.user.is_authenticated = False

        response = view_func(request, 42, name="test")

        self.assertIn(b"pk=42", response.content)
        self.assertIn(b"name=test", response.content)


@tag("utils", "cache")
@override_settings(CACHES=CACHES_OVERRIDE)
class CachePerRoleTestCase(TestCase):
    """Tests for the cache_per_role decorator."""

    def setUp(self):
        self.factory = RequestFactory()
        cache.clear()

    def tearDown(self):
        cache.clear()

    def _make_user(self, authenticated=False, is_staff=False, user_id=None):
        user = MagicMock()
        user.is_authenticated = authenticated
        user.is_staff = is_staff
        user.id = user_id
        return user

    def test_caches_anonymous_response(self):
        """Test that anonymous responses are cached under the 'anon' role."""
        call_count = {"count": 0}

        @cache_per_role(ttl=60)
        def view_func(request):
            call_count["count"] += 1
            return HttpResponse("Anon content")

        request = self.factory.get("/test/")
        request.user = self._make_user()

        view_func(request)
        view_func(request)
        self.assertEqual(call_count["count"], 1)

    def test_caches_authenticated_response(self):
        """Test that authenticated non-staff responses are cached under 'auth' role."""
        call_count = {"count": 0}

        @cache_per_role(ttl=60)
        def view_func(request):
            call_count["count"] += 1
            return HttpResponse("Auth content")

        request = self.factory.get("/test/")
        request.user = self._make_user(authenticated=True, user_id=1)

        view_func(request)
        view_func(request)
        self.assertEqual(call_count["count"], 1)

    def test_caches_staff_response(self):
        """Test that staff responses are cached under 'staff' role."""
        call_count = {"count": 0}

        @cache_per_role(ttl=60)
        def view_func(request):
            call_count["count"] += 1
            return HttpResponse("Staff content")

        request = self.factory.get("/test/")
        request.user = self._make_user(authenticated=True, is_staff=True, user_id=1)

        view_func(request)
        view_func(request)
        self.assertEqual(call_count["count"], 1)

    def test_three_roles_get_separate_entries(self):
        """Test that anon, auth, and staff each get separate cache entries."""
        call_count = {"count": 0}

        @cache_per_role(ttl=60)
        def view_func(request):
            call_count["count"] += 1
            return HttpResponse("Content")

        anon_req = self.factory.get("/test/")
        anon_req.user = self._make_user()

        auth_req = self.factory.get("/test/")
        auth_req.user = self._make_user(authenticated=True, user_id=1)

        staff_req = self.factory.get("/test/")
        staff_req.user = self._make_user(authenticated=True, is_staff=True, user_id=2)

        view_func(anon_req)
        view_func(auth_req)
        view_func(staff_req)
        self.assertEqual(call_count["count"], 3)

    def test_two_authenticated_users_share_cache(self):
        """Test that two non-staff authenticated users share the same cache entry."""
        call_count = {"count": 0}

        @cache_per_role(ttl=60)
        def view_func(request):
            call_count["count"] += 1
            return HttpResponse("Shared auth content")

        request1 = self.factory.get("/test/")
        request1.user = self._make_user(authenticated=True, user_id=1)

        request2 = self.factory.get("/test/")
        request2.user = self._make_user(authenticated=True, user_id=2)

        view_func(request1)
        view_func(request2)
        self.assertEqual(call_count["count"], 1)

    def test_two_staff_users_share_cache(self):
        """Test that two staff users share the same cache entry."""
        call_count = {"count": 0}

        @cache_per_role(ttl=60)
        def view_func(request):
            call_count["count"] += 1
            return HttpResponse("Shared staff content")

        request1 = self.factory.get("/test/")
        request1.user = self._make_user(authenticated=True, is_staff=True, user_id=1)

        request2 = self.factory.get("/test/")
        request2.user = self._make_user(authenticated=True, is_staff=True, user_id=2)

        view_func(request1)
        view_func(request2)
        self.assertEqual(call_count["count"], 1)

    def test_post_not_cached_by_default(self):
        """Test that POST requests are not cached by default."""
        call_count = {"count": 0}

        @cache_per_role(ttl=60)
        def view_func(request):
            call_count["count"] += 1
            return HttpResponse("Response")

        request = self.factory.post("/test/")
        request.user = self._make_user()

        view_func(request)
        view_func(request)
        self.assertEqual(call_count["count"], 2)

    def test_post_cached_when_enabled(self):
        """Test that POST requests are cached when cache_post=True."""
        call_count = {"count": 0}

        @cache_per_role(ttl=60, cache_post=True)
        def view_func(request):
            call_count["count"] += 1
            return HttpResponse("Response")

        request = self.factory.post("/test/")
        request.user = self._make_user()

        view_func(request)
        view_func(request)
        self.assertEqual(call_count["count"], 1)

    def test_different_paths_have_different_cache(self):
        """Test that different paths produce different cache entries."""
        call_count = {"count": 0}

        @cache_per_role(ttl=60)
        def view_func(request):
            call_count["count"] += 1
            return HttpResponse("Response")

        request1 = self.factory.get("/path1/")
        request1.user = self._make_user()

        request2 = self.factory.get("/path2/")
        request2.user = self._make_user()

        view_func(request1)
        view_func(request2)
        self.assertEqual(call_count["count"], 2)

    def test_different_query_params_have_different_cache(self):
        """Test that different query params produce different cache entries."""
        call_count = {"count": 0}

        @cache_per_role(ttl=60)
        def view_func(request):
            call_count["count"] += 1
            return HttpResponse("Response")

        request1 = self.factory.get("/test/?page=1")
        request1.user = self._make_user()

        request2 = self.factory.get("/test/?page=2")
        request2.user = self._make_user()

        view_func(request1)
        view_func(request2)
        self.assertEqual(call_count["count"], 2)

    def test_renders_template_response(self):
        """Test that TemplateResponse is rendered before caching."""

        @cache_per_role(ttl=60)
        def view_func(request):
            return TemplateResponse(request, "test_template.html", {})

        request = self.factory.get("/test/")
        request.user = self._make_user()

        with patch.object(TemplateResponse, "render") as mock_render:
            mock_render.return_value = HttpResponse("Rendered content")
            view_func(request)
            mock_render.assert_called_once()

    def test_different_languages_have_different_cache_entries(self):
        call_count = {"count": 0}

        @cache_per_role(ttl=60)
        def view_func(request):
            call_count["count"] += 1
            return HttpResponse("Response")

        request1 = self.factory.get("/test/")
        request1.user = self._make_user()
        request1.LANGUAGE_CODE = "en"

        request2 = self.factory.get("/test/")
        request2.user = self._make_user()
        request2.LANGUAGE_CODE = "de"

        view_func(request1)
        view_func(request2)
        self.assertEqual(call_count["count"], 2)

    @override_settings(ALLOWED_HOSTS=["testserver", "en.example.test", "de.example.test"])
    def test_different_hosts_have_different_cache_entries(self):
        call_count = {"count": 0}

        @cache_per_role(ttl=60)
        def view_func(request):
            call_count["count"] += 1
            return HttpResponse("Response")

        request1 = self.factory.get("/test/", HTTP_HOST="en.example.test")
        request1.user = self._make_user()

        request2 = self.factory.get("/test/", HTTP_HOST="de.example.test")
        request2.user = self._make_user()

        view_func(request1)
        view_func(request2)
        self.assertEqual(call_count["count"], 2)

    def test_set_cookie_responses_are_not_cached(self):
        call_count = {"count": 0}

        @cache_per_role(ttl=60)
        def view_func(request):
            call_count["count"] += 1
            response = HttpResponse("Response")
            response.set_cookie("sessionid", "abc")
            return response

        request = self.factory.get("/test/")
        request.user = self._make_user()

        view_func(request)
        view_func(request)
        self.assertEqual(call_count["count"], 2)

    def test_vary_cookie_responses_are_not_cached(self):
        call_count = {"count": 0}

        @cache_per_role(ttl=60)
        def view_func(request):
            call_count["count"] += 1
            response = HttpResponse("Response")
            response["Vary"] = "Cookie"
            return response

        request = self.factory.get("/test/")
        request.user = self._make_user()

        view_func(request)
        view_func(request)
        self.assertEqual(call_count["count"], 2)

    def test_uses_view_cache_prefix(self):
        """Test that cache keys use the view_cache_ prefix for signal handler compatibility."""

        @cache_per_role(ttl=60)
        def view_func(request):
            return HttpResponse("Response")

        request = self.factory.get("/laws/test/")
        request.user = self._make_user()

        view_func(request)

        cache_key = "view_cache_testserver_default_GET_/laws/test/_anon"
        self.assertIsNotNone(cache.get(cache_key))
