"""Tests for MCP tool titles/annotations and MCP Registry metadata."""

import json
import re
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase, TestCase, override_settings
from mcp_server.djangomcp import global_mcp_server
from rest_framework.test import APIClient

import oldp
from oldp.apps.mcp.annotations import READ_ONLY_HINTS, TOOL_HINTS, TOOL_TITLES

SERVER_JSON = Path(settings.BASE_DIR) / "server.json"


@override_settings(
    CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "mcp-annotation-tests",
        }
    },
)
class ToolAnnotationsTests(TestCase):
    """Every MCP tool must carry a title and read-only hints."""

    def setUp(self):
        from django.core.cache import cache

        cache.clear()

    def _list_tools(self):
        response = APIClient().post(
            "/mcp",
            data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/list"}),
            content_type="application/json",
            HTTP_ACCEPT="application/json, text/event-stream",
        )
        self.assertEqual(response.status_code, 200)
        return response.json()["result"]["tools"]

    def test_tools_list_exposes_title_and_hints(self):
        """tools/list returns a title and read-only annotations per tool."""
        tools = self._list_tools()
        self.assertGreater(len(tools), 0)
        for tool in tools:
            with self.subTest(tool=tool["name"]):
                self.assertEqual(tool.get("title"), TOOL_TITLES[tool["name"]])
                annotations = tool.get("annotations") or {}
                self.assertEqual(annotations.get("title"), tool["title"])
                expected = TOOL_HINTS.get(tool["name"], READ_ONLY_HINTS)
                for hint, value in expected.items():
                    self.assertIs(annotations.get(hint), value, hint)

    def test_every_registered_tool_has_a_title(self):
        """New tools must be added to TOOL_TITLES, and stale entries removed."""
        registered = {t.name for t in global_mcp_server._tool_manager.list_tools()}
        self.assertEqual(registered - TOOL_TITLES.keys(), set(), "tools without title")
        self.assertEqual(
            TOOL_TITLES.keys() - registered, set(), "titles for unknown tools"
        )

    def test_titles_are_short_and_unique(self):
        """Titles are distinct and short enough for client UIs."""
        titles = list(TOOL_TITLES.values())
        self.assertEqual(len(titles), len(set(titles)))
        for title in titles:
            self.assertLessEqual(len(title), 40, title)


class MCPRegistryAuthViewTests(TestCase):
    """/.well-known/mcp-registry-auth serves the configured proof record."""

    url = "/.well-known/mcp-registry-auth"

    @override_settings(MCP_REGISTRY_AUTH="")
    def test_not_configured_returns_404(self):
        self.assertEqual(self.client.get(self.url).status_code, 404)

    @override_settings(MCP_REGISTRY_AUTH="  v=MCPv1; k=ed25519; p=abc123=  ")
    def test_configured_returns_record_as_plain_text(self):
        response = self.client.get(self.url, HTTP_ACCEPT="text/plain")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response["Content-Type"].startswith("text/plain"))
        self.assertEqual(
            response.content.decode().strip(), "v=MCPv1; k=ed25519; p=abc123="
        )

    @override_settings(MCP_REGISTRY_AUTH="v=MCPv1; k=ed25519; p=abc123=")
    def test_post_not_allowed(self):
        self.assertEqual(self.client.post(self.url).status_code, 405)


class ServerJsonTests(SimpleTestCase):
    """server.json (official MCP Registry metadata) stays publishable."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.data = json.loads(SERVER_JSON.read_text())

    def test_required_fields_and_limits(self):
        """Mirror the registry schema's required fields and length limits."""
        for field in ("name", "description", "version"):
            self.assertTrue(self.data.get(field), field)
        self.assertRegex(self.data["name"], r"^[a-zA-Z0-9.-]+/[a-zA-Z0-9._-]+$")
        self.assertLessEqual(len(self.data["description"]), 100)
        self.assertLessEqual(len(self.data["title"]), 100)

    def test_version_matches_package(self):
        """The release workflow bumps server.json together with the package."""
        self.assertEqual(self.data["version"], oldp.__version__)

    def test_remote_points_at_mcp_endpoint(self):
        remotes = self.data["remotes"]
        self.assertEqual(len(remotes), 1)
        self.assertEqual(remotes[0]["type"], "streamable-http")
        self.assertTrue(re.match(r"^https://[^/]+/mcp$", remotes[0]["url"]))
