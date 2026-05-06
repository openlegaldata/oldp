"""Unit tests for platform-level MCP tools."""

from datetime import date, timedelta
from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase, override_settings

from oldp.apps.cases.models import Case
from oldp.apps.courts.models import Court
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

    def test_case_date_range_excludes_future_dated(self):
        """Regression: docs/mcp-test-report.md issue #8.

        Production reported case_date_range.latest = 2029-11-13 (a
        date-extraction artefact). The advertised "latest" should
        reflect actual recent decisions, not bogus rows.
        """
        court = Court.objects.filter(review_status="accepted").first()
        if not court:
            self.skipTest("No court fixture")
        # A "real" recent case and a bogus future-dated one.
        recent = date.today() - timedelta(days=30)
        far_future = date.today() + timedelta(days=365 * 3)
        Case.objects.create(
            court=court,
            file_number="REC 001/24",
            date=recent,
            content="<p>recent</p>",
            slug="recent-test",
            review_status="accepted",
        )
        Case.objects.create(
            court=court,
            file_number="FUT 001/99",
            date=far_future,
            content="<p>bogus future</p>",
            slug="future-test",
            review_status="accepted",
        )

        result = self.tools.get_platform_info()
        latest = result["data_coverage"]["case_date_range"]["latest"]
        self.assertEqual(
            latest,
            str(recent),
            msg=(
                f"Expected case_date_range.latest == {recent}, got {latest}. "
                "Future-dated rows are leaking into the date range."
            ),
        )

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
