"""Unit tests for court MCP tools."""

from django.test import TestCase, override_settings

from oldp.apps.courts.mcp import CourtTools
from oldp.apps.courts.models import Court


@override_settings(
    CACHES={"default": {"BACKEND": "django.core.cache.backends.dummy.DummyCache"}}
)
class CourtToolsTests(TestCase):
    """Tests for list_courts and get_court MCP tools."""

    fixtures = [
        "locations/countries.json",
        "locations/states.json",
        "locations/cities.json",
        "courts/courts.json",
    ]

    def setUp(self):
        self.tools = CourtTools()

    def test_list_courts_returns_results(self):
        result = self.tools.list_courts()
        self.assertIn("results", result)
        self.assertIsInstance(result["results"], list)

    def test_list_courts_result_has_required_fields(self):
        result = self.tools.list_courts()
        if result["results"]:
            court = result["results"][0]
            self.assertIn("id", court)
            self.assertIn("name", court)
            self.assertIn("slug", court)
            self.assertIn("court_type", court)
            self.assertIn("state", court)

    def test_list_courts_filter_by_court_type(self):
        # Get a known court type from fixtures
        court = Court.objects.filter(
            court_type__isnull=False, review_status="accepted"
        ).first()
        if court and court.court_type:
            result = self.tools.list_courts(court_type=court.court_type)
            self.assertIn("results", result)
            for c in result["results"]:
                self.assertEqual(c["court_type"].lower(), court.court_type.lower())

    def test_list_courts_limit(self):
        result = self.tools.list_courts(limit=3)
        self.assertLessEqual(len(result["results"]), 3)

    def test_list_courts_limit_capped_at_100(self):
        result = self.tools.list_courts(limit=999)
        self.assertLessEqual(len(result["results"]), 100)

    def test_list_courts_no_results_message(self):
        result = self.tools.list_courts(search="zzz_nonexistent_court_zzz")
        self.assertIn("message", result)

    def test_get_court_by_id(self):
        court = Court.objects.filter(review_status="accepted").first()
        if court:
            result = self.tools.get_court(court_id=court.id)
            self.assertEqual(result["id"], court.id)
            self.assertEqual(result["name"], court.name)

    def test_get_court_by_slug(self):
        court = Court.objects.filter(review_status="accepted").first()
        if court:
            result = self.tools.get_court(slug=court.slug)
            self.assertEqual(result["id"], court.id)

    def test_get_court_by_code(self):
        court = (
            Court.objects.filter(review_status="accepted", code__isnull=False)
            .exclude(code="")
            .first()
        )
        if court:
            result = self.tools.get_court(code=court.code)
            self.assertEqual(result["id"], court.id)

    def test_get_court_not_found(self):
        result = self.tools.get_court(court_id=999999)
        self.assertIn("error", result)

    def test_get_court_no_params(self):
        result = self.tools.get_court()
        self.assertIn("error", result)

    def test_get_court_has_contact_info(self):
        court = Court.objects.filter(review_status="accepted").first()
        if court:
            result = self.tools.get_court(court_id=court.id)
            self.assertIn("homepage", result)
            self.assertIn("telephone", result)
            self.assertIn("case_count", result)
