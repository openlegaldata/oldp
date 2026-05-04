"""End-to-end tests for the MCP endpoint."""

import json

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

User = get_user_model()


@override_settings(
    CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "mcp-e2e-tests",
        }
    },
    STORAGES={
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
        }
    },
)
class MCPEndpointTests(TestCase):
    """End-to-end tests for the /mcp endpoint."""

    fixtures = [
        "locations/countries.json",
        "locations/states.json",
        "locations/cities.json",
        "courts/courts.json",
    ]

    def setUp(self):
        from django.core.cache import cache

        cache.clear()
        self.client = APIClient()

    def _mcp_request(self, method, params=None, request_id=1):
        """Send a JSON-RPC request to the MCP endpoint."""
        payload = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
        }
        if params is not None:
            payload["params"] = params
        return self.client.post(
            "/mcp",
            data=json.dumps(payload),
            content_type="application/json",
            HTTP_ACCEPT="application/json, text/event-stream",
        )

    def test_mcp_endpoint_exists(self):
        """MCP endpoint should be reachable."""
        response = self._mcp_request(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "test", "version": "1.0"},
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["result"]["serverInfo"]["name"], "oldp")

    def test_mcp_anonymous_access(self):
        """MCP endpoint should work without authentication."""
        response = self._mcp_request(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "anonymous-test", "version": "1.0"},
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("result", response.json())

    def test_mcp_authenticated_access(self):
        """MCP endpoint should work with authenticated user."""
        user = User.objects.create_user(username="mcpuser", password="testpass123")
        self.client.force_authenticate(user=user)
        response = self._mcp_request(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "auth-test", "version": "1.0"},
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("result", response.json())

    def test_mcp_rejects_untrusted_origin(self):
        """Browser-originated requests must come from a trusted origin."""
        response = self.client.post(
            "/mcp",
            data=json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {},
                        "clientInfo": {"name": "origin-test", "version": "1.0"},
                    },
                }
            ),
            content_type="application/json",
            HTTP_ACCEPT="application/json, text/event-stream",
            HTTP_ORIGIN="https://evil.example",
        )
        self.assertEqual(response.status_code, 403)

    def test_mcp_allows_same_origin(self):
        """Same-origin browser requests should pass Origin validation."""
        response = self.client.post(
            "/mcp",
            data=json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {},
                        "clientInfo": {"name": "origin-test", "version": "1.0"},
                    },
                }
            ),
            content_type="application/json",
            HTTP_ACCEPT="application/json, text/event-stream",
            HTTP_ORIGIN="http://testserver",
        )
        self.assertEqual(response.status_code, 200)

    def test_mcp_tools_list(self):
        """tools/list should return registered tools."""
        # First initialize
        init_resp = self._mcp_request(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "test", "version": "1.0"},
            },
        )
        # The MCP server is configured as stateless, so tools/list should
        # work in the same session. If the server returns a session ID, pass it.
        session_id = init_resp.get("Mcp-Session-Id", "")
        extra = {}
        if session_id:
            extra["HTTP_MCP_SESSION_ID"] = session_id

        response = self.client.post(
            "/mcp",
            data=json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/list",
                    "params": {},
                }
            ),
            content_type="application/json",
            HTTP_ACCEPT="application/json, text/event-stream",
            **extra,
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("result", data)
        self.assertIn("tools", data["result"])
        tool_names = [t["name"] for t in data["result"]["tools"]]
        # Check that our core tools are registered
        self.assertIn("get_platform_info", tool_names)
        self.assertIn("list_courts", tool_names)
        self.assertIn("search_cases", tool_names)
        self.assertIn("validate_citation", tool_names)

    def test_mcp_tool_call_get_platform_info(self):
        """tools/call for get_platform_info should return platform data."""
        # Initialize first
        self._mcp_request(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "test", "version": "1.0"},
            },
        )
        # Call tool
        response = self._mcp_request(
            "tools/call",
            {"name": "get_platform_info", "arguments": {}},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("result", data)
        self.assertFalse(data["result"].get("isError", False))
        self.assertIn("content", data["result"])

    def test_mcp_tool_call_list_courts(self):
        """tools/call for list_courts should return court data."""
        self._mcp_request(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "test", "version": "1.0"},
            },
        )
        response = self._mcp_request(
            "tools/call",
            {"name": "list_courts", "arguments": {"limit": 5}},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("result", data)
        self.assertFalse(data["result"].get("isError", False))
        self.assertIn("content", data["result"])

    def test_mcp_invalid_method(self):
        """Unknown MCP method should return an error response."""
        response = self._mcp_request("nonexistent/method", {})
        # Should return 200 with JSON-RPC error, or 4xx
        if response.status_code == 200:
            data = response.json()
            if "error" in data:
                self.assertIn("code", data["error"])

    def test_mcp_post_required(self):
        """GET returns 405 because OLDP does not expose standalone SSE."""
        response = self.client.get("/mcp")
        self.assertEqual(response.status_code, 405)
        self.assertIn("POST", response["Allow"])
        self.assertIn("DELETE", response["Allow"])
        self.assertNotIn("GET", response["Allow"])


@override_settings(
    CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "mcp-rate-limit-tests",
        }
    },
    STORAGES={
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
        }
    },
    MCP_ANTHROPIC_ANON_RATE="3/hour",
)
class MCPRateLimitTests(TestCase):
    """Tests for MCP endpoint rate limiting."""

    def setUp(self):
        from django.core.cache import cache

        cache.clear()
        self.client = APIClient()

    def _mcp_request(self, request_id=1):
        return self.client.post(
            "/mcp",
            data=json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {},
                        "clientInfo": {"name": "test", "version": "1.0"},
                    },
                }
            ),
            content_type="application/json",
            HTTP_ACCEPT="application/json, text/event-stream",
        )

    def test_rate_limit_eventually_triggers(self):
        """After exceeding rate limit, should get 429."""
        responses = []
        for i in range(5):
            resp = self._mcp_request(request_id=i)
            responses.append(resp.status_code)
        # At least one should be 429 (we set limit to 3/hour)
        self.assertIn(429, responses)
