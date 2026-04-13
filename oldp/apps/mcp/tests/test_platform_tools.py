"""Unit tests for platform-level MCP tools."""

from django.test import TestCase, override_settings

from oldp.apps.mcp.mcp import PlatformTools


@override_settings(
    CACHES={"default": {"BACKEND": "django.core.cache.backends.dummy.DummyCache"}}
)
class PlatformToolsTests(TestCase):
    """Tests for get_platform_info tool."""

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
