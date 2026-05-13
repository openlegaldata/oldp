"""Tests for AnonymousPublicCacheMiddleware."""

from unittest.mock import MagicMock

from django.http import HttpResponse
from django.test import RequestFactory, TestCase, override_settings, tag

from oldp.utils.middleware import AnonymousPublicCacheMiddleware


def _anon(req):
    user = MagicMock()
    user.is_anonymous = True
    req.user = user
    return req


def _authed(req):
    user = MagicMock()
    user.is_anonymous = False
    req.user = user
    return req


@tag("utils", "middleware")
class AnonymousPublicCacheMiddlewareTestCase(TestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def _build(self, response: HttpResponse):
        def get_response(request):
            return response

        return AnonymousPublicCacheMiddleware(get_response)

    def _response_with_cookie_and_vary(self) -> HttpResponse:
        resp = HttpResponse("body")
        resp["Vary"] = "Cookie"
        resp.set_cookie("csrftoken", "abc123")
        return resp

    def test_rewrites_anon_get_on_cacheable_prefix(self):
        mw = self._build(self._response_with_cookie_and_vary())
        request = _anon(self.factory.get("/case/lg-foo-2024-01-01"))
        response = mw(request)
        self.assertEqual(response["Vary"], "Accept-Encoding")
        self.assertNotIn("csrftoken", response.cookies)
        self.assertIn("public", response["Cache-Control"])
        self.assertIn("s-maxage=", response["Cache-Control"])

    def test_rewrites_anon_get_on_homepage(self):
        mw = self._build(self._response_with_cookie_and_vary())
        request = _anon(self.factory.get("/"))
        response = mw(request)
        self.assertEqual(response["Vary"], "Accept-Encoding")
        self.assertIn("public", response["Cache-Control"])

    def test_skips_authenticated_user(self):
        mw = self._build(self._response_with_cookie_and_vary())
        request = _authed(self.factory.get("/case/lg-foo-2024-01-01"))
        response = mw(request)
        self.assertEqual(response["Vary"], "Cookie")
        self.assertIn("csrftoken", response.cookies)
        self.assertNotIn("Cache-Control", response.headers)

    def test_skips_non_cacheable_path(self):
        mw = self._build(self._response_with_cookie_and_vary())
        request = _anon(self.factory.get("/api/cases/"))
        response = mw(request)
        self.assertEqual(response["Vary"], "Cookie")
        self.assertIn("csrftoken", response.cookies)

    def test_skips_non_200(self):
        resp = HttpResponse("not found", status=404)
        resp["Vary"] = "Cookie"
        resp.set_cookie("csrftoken", "abc123")
        mw = self._build(resp)
        request = _anon(self.factory.get("/case/missing"))
        response = mw(request)
        self.assertEqual(response["Vary"], "Cookie")
        self.assertIn("csrftoken", response.cookies)

    def test_skips_post(self):
        mw = self._build(self._response_with_cookie_and_vary())
        request = _anon(self.factory.post("/case/lg-foo-2024-01-01"))
        response = mw(request)
        self.assertEqual(response["Vary"], "Cookie")
        self.assertIn("csrftoken", response.cookies)

    @override_settings(ANON_CACHE_ENABLED=False)
    def test_kill_switch(self):
        mw = self._build(self._response_with_cookie_and_vary())
        request = _anon(self.factory.get("/case/lg-foo-2024-01-01"))
        response = mw(request)
        self.assertEqual(response["Vary"], "Cookie")
        self.assertIn("csrftoken", response.cookies)

    @override_settings(
        ANON_CACHE_PATH_PREFIXES=("/custom/",),
        ANON_CACHE_PATHS_EXACT=(),
    )
    def test_custom_prefix_setting(self):
        mw = self._build(self._response_with_cookie_and_vary())
        # Default-cacheable path no longer matches
        request = _anon(self.factory.get("/case/lg-foo-2024-01-01"))
        response = mw(request)
        self.assertEqual(response["Vary"], "Cookie")

        # Custom-configured prefix now matches
        mw2 = self._build(self._response_with_cookie_and_vary())
        request2 = _anon(self.factory.get("/custom/foo"))
        response2 = mw2(request2)
        self.assertEqual(response2["Vary"], "Accept-Encoding")

    @override_settings(ANON_CACHE_S_MAXAGE=120, ANON_CACHE_MAX_AGE=10)
    def test_custom_ttl_settings(self):
        mw = self._build(self._response_with_cookie_and_vary())
        request = _anon(self.factory.get("/case/foo"))
        response = mw(request)
        self.assertIn("s-maxage=120", response["Cache-Control"])
        self.assertIn("max-age=10", response["Cache-Control"])
