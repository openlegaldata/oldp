"""Unit tests for MCP throttle classes."""

from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase, override_settings

from oldp.apps.mcp.throttles import MCPAnonThrottle, MCPUserThrottle, _is_anthropic_ip

User = get_user_model()


class AnthropicIPDetectionTests(TestCase):
    """Tests for Anthropic IP address detection."""

    def test_anthropic_ip_in_range(self):
        self.assertTrue(_is_anthropic_ip("160.79.104.1"))

    def test_anthropic_ip_at_boundary(self):
        self.assertTrue(_is_anthropic_ip("160.79.104.0"))
        self.assertTrue(_is_anthropic_ip("160.79.111.255"))

    def test_non_anthropic_ip(self):
        self.assertFalse(_is_anthropic_ip("8.8.8.8"))
        self.assertFalse(_is_anthropic_ip("192.168.1.1"))

    def test_invalid_ip(self):
        self.assertFalse(_is_anthropic_ip("not-an-ip"))
        self.assertFalse(_is_anthropic_ip(""))
        self.assertFalse(_is_anthropic_ip(None))


@override_settings(
    CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "throttle-tests",
        }
    }
)
class MCPAnonThrottleTests(TestCase):
    """Tests for anonymous MCP request throttling."""

    def setUp(self):
        from django.core.cache import cache

        cache.clear()
        self.factory = RequestFactory()
        self.throttle = MCPAnonThrottle()

    def test_returns_none_for_authenticated_user(self):
        request = self.factory.get("/mcp")
        request.user = User(pk=1, username="test")
        request.META["REMOTE_ADDR"] = "1.2.3.4"
        key = self.throttle.get_cache_key(request, None)
        self.assertIsNone(key)

    def test_shared_bucket_for_anthropic_ip(self):
        request = self.factory.get("/mcp")
        request.user = None
        request.META["REMOTE_ADDR"] = "160.79.104.10"
        key = self.throttle.get_cache_key(request, None)
        self.assertEqual(key, "throttle_mcp_anthropic_anon")

    def test_per_ip_bucket_for_regular_ip(self):
        request = self.factory.get("/mcp")
        request.user = None
        request.META["REMOTE_ADDR"] = "8.8.8.8"
        key = self.throttle.get_cache_key(request, None)
        self.assertIn("8.8.8.8", key)

    def test_get_rate_default(self):
        self.assertEqual(self.throttle.get_rate(), "500/hour")

    @override_settings(MCP_ANTHROPIC_ANON_RATE="100/hour")
    def test_get_rate_from_settings(self):
        self.assertEqual(self.throttle.get_rate(), "100/hour")


@override_settings(
    CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "throttle-tests-user",
        }
    }
)
class MCPUserThrottleTests(TestCase):
    """Tests for authenticated MCP user throttling."""

    def setUp(self):
        from django.core.cache import cache

        cache.clear()
        self.factory = RequestFactory()
        self.throttle = MCPUserThrottle()

    def test_returns_none_for_anonymous(self):
        request = self.factory.get("/mcp")
        request.user = None
        key = self.throttle.get_cache_key(request, None)
        self.assertIsNone(key)

    def test_per_user_bucket(self):
        request = self.factory.get("/mcp")
        request.user = User(pk=42, username="testuser")
        key = self.throttle.get_cache_key(request, None)
        self.assertIn("42", key)

    def test_get_rate_default(self):
        self.assertEqual(self.throttle.get_rate(), "1000/hour")

    @override_settings(MCP_USER_RATE="2000/hour")
    def test_get_rate_from_settings(self):
        self.assertEqual(self.throttle.get_rate(), "2000/hour")
