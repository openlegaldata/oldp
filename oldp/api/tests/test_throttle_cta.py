"""Tests for the 429 upgrade call-to-action (REST + MCP)."""

from django.contrib.auth.models import AnonymousUser, User
from django.core.cache import cache
from django.test import RequestFactory, TestCase, override_settings
from rest_framework.exceptions import NotFound, Throttled
from rest_framework.test import APIClient

from oldp.api.exceptions import full_details_exception_handler
from oldp.apps.accounts.models import APIToken
from oldp.apps.mcp.views import OLDPMCPView

LOCMEM_CACHE = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}

API_ENDPOINT = "/api/"


def _rf(anon_rate, user_rate):
    return {
        "DEFAULT_PERMISSION_CLASSES": [
            "rest_framework.permissions.DjangoModelPermissionsOrAnonReadOnly"
        ],
        "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.LimitOffsetPagination",
        "DEFAULT_FILTER_BACKENDS": (
            "django_filters.rest_framework.DjangoFilterBackend",
        ),
        "PAGE_SIZE": 50,
        "DEFAULT_RENDERER_CLASSES": ("rest_framework.renderers.JSONRenderer",),
        "DEFAULT_AUTHENTICATION_CLASSES": (
            "oldp.apps.accounts.authentication.CombinedTokenAuthentication",
            "rest_framework.authentication.SessionAuthentication",
        ),
        "DEFAULT_THROTTLE_CLASSES": (
            "rest_framework.throttling.AnonRateThrottle",
            "oldp.api.throttling.TokenUserRateThrottle",
        ),
        "DEFAULT_THROTTLE_RATES": {"anon": anon_rate, "user": user_rate},
        "EXCEPTION_HANDLER": "oldp.api.exceptions.full_details_exception_handler",
    }


@override_settings(CACHES=LOCMEM_CACHE, REST_FRAMEWORK=_rf("2/day", "2/hour"))
class RestThrottleCtaTestCase(TestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user("cta_user", password="testpass123")
        self.token = APIToken.objects.create(user=self.user, name="t")
        self.client = APIClient()

    def tearDown(self):
        cache.clear()

    def _exhaust(self, client, n):
        last = None
        for _ in range(n):
            last = client.get(API_ENDPOINT)
        return last

    def test_authenticated_free_user_cta(self):
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.token.key}")
        res = self._exhaust(self.client, 3)
        self.assertEqual(res.status_code, 429)
        upgrade = res.data["upgrade"]
        self.assertIn("production access", upgrade["message"])
        self.assertIn("/contact/", upgrade["contact_url"])
        self.assertNotIn("register_url", upgrade)
        self.assertIn("retry_after", res.data)
        self.assertIsInstance(res.data["retry_after"], int)

    def test_custom_token_cta_mentions_contracted_limit(self):
        self.token.rate_limit = 1
        self.token.save()
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.token.key}")
        res = self._exhaust(self.client, 2)
        self.assertEqual(res.status_code, 429)
        self.assertIn("contracted limit", res.data["upgrade"]["message"])

    def test_non_throttle_error_has_no_upgrade(self):
        # A 404 must not carry the upgrade block.
        res = self.client.get("/api/cases/999999999/")
        self.assertEqual(res.status_code, 404)
        self.assertNotIn("upgrade", res.data)


class HandlerUnitTestCase(TestCase):
    """Directly exercise the handler for surface/branch detection."""

    def setUp(self):
        self.factory = RequestFactory()

    def _handle(self, view, user=None, auth=None):
        request = self.factory.get("/")
        request.user = user or AnonymousUser()
        request.auth = auth
        exc = Throttled(wait=42)
        return full_details_exception_handler(exc, {"request": request, "view": view})

    def test_mcp_view_gets_mcp_message(self):
        res = self._handle(OLDPMCPView())
        self.assertIn("MCP", res.data["upgrade"]["message"])
        self.assertEqual(res.data["retry_after"], 42)

    def test_rest_view_is_not_mcp(self):
        class DummyView:
            pass

        res = self._handle(DummyView())
        self.assertNotIn("MCP", res.data["upgrade"]["message"])

    def test_anonymous_rest_cta_offers_registration(self):
        # Anonymous REST 429s can't be driven via the client (anon GETs are
        # cached before the throttle), so assert the branch at handler level.
        class DummyView:
            pass

        res = self._handle(DummyView(), user=AnonymousUser())
        upgrade = res.data["upgrade"]
        self.assertIn("Register", upgrade["message"])
        self.assertIn("/accounts/signup/", upgrade["register_url"])
        self.assertNotIn("MCP", upgrade["message"])

    def test_non_throttled_passthrough(self):
        res = full_details_exception_handler(NotFound(), {"request": None})
        self.assertNotIn("upgrade", res.data)
