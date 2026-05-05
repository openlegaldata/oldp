"""Unit tests for platform-level MCP tools."""

from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase, override_settings

from oldp.apps.mcp.mcp import PlatformTools


@override_settings(
    CACHES={"default": {"BACKEND": "django.core.cache.backends.dummy.DummyCache"}}
)
class PlatformToolsTests(TestCase):
    """Tests for get_platform_info tool (cache disabled)."""

    fixtures = [
        "locations/countries.json",
        "locations/states.json",
        "locations/cities.json",
        "courts/courts.json",
    ]

    def setUp(self):
        self.tools = PlatformTools()

    def test_get_platform_info_returns_dict(self):
        result = self.tools.get_platform_info()
        self.assertIsInstance(result, dict)

    def test_get_platform_info_has_required_keys(self):
        result = self.tools.get_platform_info()
        self.assertIn("platform", result)
        self.assertIn("data_coverage", result)
        self.assertIn("available_tools", result)
        self.assertIn("disclaimer", result)

    def test_data_coverage_has_counts(self):
        result = self.tools.get_platform_info()
        coverage = result["data_coverage"]
        self.assertIn("total_cases", coverage)
        self.assertIn("total_courts", coverage)
        self.assertIn("total_law_books", coverage)
        self.assertIn("total_law_sections", coverage)
        self.assertIn("total_references", coverage)
        # Counts should be non-negative integers
        self.assertGreaterEqual(coverage["total_cases"], 0)
        self.assertGreaterEqual(coverage["total_courts"], 0)

    def test_available_tools_categories(self):
        result = self.tools.get_platform_info()
        tools = result["available_tools"]
        self.assertIn("discovery", tools)
        self.assertIn("search", tools)
        self.assertIn("retrieval", tools)
        self.assertIn("cross_references", tools)
        self.assertIn("statistics", tools)


@override_settings(
    CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "platform-info-cache-tests",
        }
    },
    MCP_PLATFORM_INFO_CACHE_TTL=60,
)
class PlatformInfoCachingTests(TestCase):
    """Verify ``get_platform_info`` caches its expensive aggregate queries."""

    fixtures = [
        "locations/countries.json",
        "locations/states.json",
        "locations/cities.json",
        "courts/courts.json",
    ]

    def setUp(self):
        cache.clear()
        self.tools = PlatformTools()

    def test_second_call_uses_cache(self):
        """The second invocation should hit the cache and skip DB aggregates."""
        with patch.object(
            PlatformTools,
            "_build_platform_info",
            wraps=PlatformTools._build_platform_info,
        ) as spy:
            first = self.tools.get_platform_info()
            second = self.tools.get_platform_info()

        self.assertEqual(first, second)
        self.assertEqual(spy.call_count, 1)

    def test_cache_returns_equivalent_payload(self):
        first = self.tools.get_platform_info()
        second = self.tools.get_platform_info()
        # Must be equal and include the same top-level keys in both calls.
        self.assertEqual(set(first.keys()), set(second.keys()))
        self.assertEqual(
            first["data_coverage"]["total_courts"],
            second["data_coverage"]["total_courts"],
        )
