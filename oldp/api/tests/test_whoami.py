"""Tests for the caller identity + rate-limit budget (REST + MCP whoami)."""

import json
from datetime import timedelta

from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import RequestFactory, TestCase, override_settings
from django.utils import timezone
from oauth2_provider.models import AccessToken, get_application_model
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from oldp.api.throttling import TokenUserRateThrottle
from oldp.api.whoami import rate_limit_status
from oldp.apps.accounts.models import APIToken
from oldp.apps.mcp.throttles import MCP_THROTTLE_CLASSES

LOCMEM_CACHE = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "whoami-tests",
    }
}
STORAGES = {
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
    }
}
ANTHROPIC_IP = "160.79.104.10"


def _rf(anon="5/day", user="4/hour", enriched="8/hour"):
    return {
        "DEFAULT_AUTHENTICATION_CLASSES": (
            "oldp.apps.accounts.authentication.CombinedTokenAuthentication",
            "rest_framework.authentication.SessionAuthentication",
        ),
        "DEFAULT_THROTTLE_CLASSES": (
            "rest_framework.throttling.AnonRateThrottle",
            "oldp.api.throttling.TokenUserRateThrottle",
        ),
        "DEFAULT_THROTTLE_RATES": {"anon": anon, "user": user, "enriched": enriched},
        "DEFAULT_RENDERER_CLASSES": ("rest_framework.renderers.JSONRenderer",),
        "EXCEPTION_HANDLER": "oldp.api.exceptions.full_details_exception_handler",
    }


@override_settings(
    CACHES=LOCMEM_CACHE, REST_FRAMEWORK=_rf(), SITE_URL="https://example.org"
)
class RestWhoAmITests(TestCase):
    """GET /api/whoami/ for anonymous and authenticated callers."""

    def setUp(self):
        cache.clear()
        # AnonRateThrottle reads its rates at import time; point it at ours.
        from rest_framework.throttling import AnonRateThrottle

        self._anon_rates = AnonRateThrottle.THROTTLE_RATES
        AnonRateThrottle.THROTTLE_RATES = _rf()["DEFAULT_THROTTLE_RATES"]
        self.client = APIClient()
        self.user = User.objects.create_user("whoami_user", password="pw")

    def tearDown(self):
        from rest_framework.throttling import AnonRateThrottle

        AnonRateThrottle.THROTTLE_RATES = self._anon_rates
        cache.clear()

    def _get(self, **extra):
        response = self.client.get("/api/whoami/", **extra)
        self.assertEqual(response.status_code, 200, response.content)
        return response

    def test_anonymous(self):
        response = self._get()
        data = response.json()
        self.assertFalse(data["authenticated"])
        self.assertIsNone(data["user"])
        self.assertIsNone(data["auth_method"])
        self.assertEqual(
            data["rate_limit"],
            {
                "tier": "anonymous",
                "bucket": "ip",
                "limit": 5,
                "window_seconds": 86400,
                "used": 1,
                "remaining": 4,
                "retry_after_seconds": None,
            },
        )
        self.assertEqual(data["upgrade"]["action"], "sign_up")
        self.assertEqual(data["upgrade"]["limit"], "4 requests/hour")
        self.assertTrue(data["upgrade"]["url"].startswith("https://example.org/"))
        self.assertIn("private", response["Cache-Control"])
        self.assertIn("no-store", response["Cache-Control"])

    def test_registered_api_token_counts_shared_budget(self):
        token = APIToken.objects.create(user=self.user, name="t")
        auth = {"HTTP_AUTHORIZATION": f"Token {token.key}"}
        self.client.get("/api/whoami/", **auth)
        data = self._get(**auth).json()
        self.assertTrue(data["authenticated"])
        self.assertEqual(
            data["user"], {"username": "whoami_user", "profile_complete": False}
        )
        self.assertEqual(data["auth_method"], "api_token")
        self.assertEqual(data["rate_limit"]["tier"], "registered")
        self.assertEqual(data["rate_limit"]["bucket"], "user")
        self.assertEqual(data["rate_limit"]["limit"], 4)
        self.assertEqual(data["rate_limit"]["used"], 2)
        self.assertEqual(data["rate_limit"]["remaining"], 2)
        self.assertEqual(data["upgrade"]["action"], "complete_profile")
        self.assertEqual(data["upgrade"]["limit"], "8 requests/hour")

    def test_legacy_token(self):
        token, _ = Token.objects.get_or_create(user=self.user)
        data = self._get(HTTP_AUTHORIZATION=f"Token {token.key}").json()
        self.assertEqual(data["auth_method"], "legacy_token")

    def test_enriched_profile(self):
        profile = self.user.profile
        profile.enriched_at = timezone.now()
        profile.save()
        self.client.force_login(self.user)
        data = self._get().json()
        self.assertEqual(data["auth_method"], "session")
        self.assertEqual(data["rate_limit"]["tier"], "enriched")
        self.assertEqual(data["rate_limit"]["limit"], 8)
        self.assertIsNone(data["upgrade"])

    def test_custom_token_rate(self):
        token = APIToken.objects.create(user=self.user, name="big", rate_limit=50)
        data = self._get(HTTP_AUTHORIZATION=f"Token {token.key}").json()
        self.assertEqual(data["rate_limit"]["tier"], "custom")
        self.assertEqual(data["rate_limit"]["limit"], 50)
        self.assertIsNone(data["upgrade"])


@override_settings(CACHES=LOCMEM_CACHE, REST_FRAMEWORK=_rf(user="2/hour"))
class RateLimitStatusTests(TestCase):
    """rate_limit_status reads the bucket without recording a request."""

    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user("budget_user")
        self.request = RequestFactory().get("/")
        self.request.user = self.user
        self.request.auth = None

    def test_exhausted_budget_reports_retry_after(self):
        throttle = TokenUserRateThrottle()
        self.assertTrue(throttle.allow_request(self.request, None))
        self.assertTrue(throttle.allow_request(self.request, None))

        status = rate_limit_status(self.request, [TokenUserRateThrottle()])
        self.assertEqual(status["used"], 2)
        self.assertEqual(status["remaining"], 0)
        self.assertGreater(status["retry_after_seconds"], 3500)
        self.assertLessEqual(status["retry_after_seconds"], 3600)

    def test_reading_does_not_consume(self):
        for _ in range(3):
            status = rate_limit_status(self.request, [TokenUserRateThrottle()])
        self.assertEqual(status["used"], 0)
        self.assertEqual(status["remaining"], 2)
        self.assertIsNone(status["retry_after_seconds"])

    def test_request_without_meta_has_no_status(self):
        self.assertIsNone(rate_limit_status(object(), [TokenUserRateThrottle()]))


@override_settings(
    CACHES=LOCMEM_CACHE,
    STORAGES=STORAGES,
    REST_FRAMEWORK=_rf(),
    MCP_ANTHROPIC_ANON_RATE="30/hour",
    SITE_URL="https://example.org",
)
class MCPWhoAmITests(TestCase):
    """The whoami MCP tool, called end to end through /mcp."""

    def setUp(self):
        cache.clear()
        self.client = APIClient()

    def _call_whoami(self, **extra):
        response = self.client.post(
            "/mcp",
            data=json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "tools/call",
                    "params": {"name": "whoami", "arguments": {}},
                }
            ),
            content_type="application/json",
            HTTP_ACCEPT="application/json, text/event-stream",
            **extra,
        )
        self.assertEqual(response.status_code, 200, response.content)
        result = response.json()["result"]
        self.assertFalse(result.get("isError", False), result)
        return json.loads(result["content"][0]["text"])

    def test_anonymous_connector_shares_one_bucket(self):
        self._call_whoami(REMOTE_ADDR=ANTHROPIC_IP)
        data = self._call_whoami(REMOTE_ADDR="160.79.104.99")
        self.assertFalse(data["authenticated"])
        self.assertEqual(data["rate_limit"]["tier"], "anonymous")
        self.assertEqual(data["rate_limit"]["bucket"], "shared")
        self.assertEqual(data["rate_limit"]["limit"], 30)
        self.assertEqual(data["rate_limit"]["used"], 2)
        self.assertEqual(data["upgrade"]["action"], "sign_up")
        self.assertIn("share one budget", data["upgrade"]["message"])

    def test_anonymous_other_client_has_own_bucket(self):
        data = self._call_whoami(REMOTE_ADDR="203.0.113.5")
        self.assertEqual(data["rate_limit"]["bucket"], "ip")
        self.assertNotIn("share one budget", data["upgrade"]["message"])

    def test_oauth_user(self):
        user = User.objects.create_user("mcp_whoami_user")
        app = get_application_model().objects.create(
            name="whoami test",
            user=user,
            client_type="public",
            authorization_grant_type="authorization-code",
            redirect_uris="https://example.com/callback",
        )
        token = AccessToken.objects.create(
            user=user,
            application=app,
            token="whoami-oauth-token",
            expires=timezone.now() + timedelta(hours=1),
            scope="read",
        )
        data = self._call_whoami(HTTP_AUTHORIZATION=f"Bearer {token.token}")
        self.assertTrue(data["authenticated"])
        self.assertEqual(data["user"]["username"], "mcp_whoami_user")
        self.assertEqual(data["auth_method"], "oauth")
        self.assertEqual(data["rate_limit"]["tier"], "registered")
        self.assertEqual(data["rate_limit"]["bucket"], "user")
        self.assertEqual(data["rate_limit"]["used"], 1)

    def test_mcp_throttle_list_is_what_the_view_enforces(self):
        from oldp.apps.mcp.views import OLDPMCPView

        self.assertEqual(OLDPMCPView.throttle_classes, MCP_THROTTLE_CLASSES)
