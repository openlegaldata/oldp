"""Unit tests for case MCP tools."""

from datetime import date

from django.test import TestCase, override_settings

from oldp.apps.cases.mcp import CaseTools
from oldp.apps.cases.models import Case
from oldp.apps.courts.models import Court


@override_settings(
    CACHES={"default": {"BACKEND": "django.core.cache.backends.dummy.DummyCache"}}
)
class CaseToolsTests(TestCase):
    """Tests for case search, filter, retrieval, and statistics MCP tools."""

    fixtures = [
        "locations/countries.json",
        "locations/states.json",
        "locations/cities.json",
        "courts/courts.json",
    ]

    def setUp(self):
        self.tools = CaseTools()
        self.court = Court.objects.filter(review_status="accepted").first()
        # Create test cases
        if self.court:
            self.case1 = Case.objects.create(
                court=self.court,
                file_number="I ZR 100/21",
                date=date(2023, 6, 15),
                content="<p>This is a test case about tort law.</p>",
                type="Urteil",
                ecli="ECLI:DE:BGH:2023:150623UIZR100.21.0",
                slug="test-case-1",
                review_status="accepted",
            )
            self.case2 = Case.objects.create(
                court=self.court,
                file_number="II ZR 200/22",
                date=date(2024, 3, 10),
                content="<p>Another test case about contract law.</p>",
                type="Beschluss",
                slug="test-case-2",
                review_status="accepted",
            )
            self.pending_case = Case.objects.create(
                court=self.court,
                file_number="III ZR 300/23",
                date=date(2024, 1, 1),
                content="<p>Pending case.</p>",
                slug="test-case-pending",
                review_status="pending",
            )

    # --- filter_cases tests ---

    def test_filter_cases_returns_results(self):
        result = self.tools.filter_cases()
        self.assertIn("results", result)
        self.assertIn("total", result)

    def test_filter_cases_by_court(self):
        if self.court:
            result = self.tools.filter_cases(court_id=self.court.id)
            for c in result["results"]:
                self.assertIsNotNone(c["court_name"])

    def test_filter_cases_by_file_number(self):
        result = self.tools.filter_cases(file_number="I ZR 100/21")
        self.assertEqual(result["total"], 1)
        self.assertEqual(result["results"][0]["file_number"], "I ZR 100/21")

    def test_filter_cases_by_ecli(self):
        result = self.tools.filter_cases(ecli="ECLI:DE:BGH:2023:150623UIZR100.21.0")
        self.assertEqual(result["total"], 1)

    def test_filter_cases_by_date_range(self):
        result = self.tools.filter_cases(
            date_after="2024-01-01", date_before="2024-12-31"
        )
        for c in result["results"]:
            self.assertGreaterEqual(c["date"], "2024-01-01")
            self.assertLessEqual(c["date"], "2024-12-31")

    def test_filter_cases_by_decision_type(self):
        result = self.tools.filter_cases(decision_type="Urteil")
        for c in result["results"]:
            self.assertIn("Urteil", c["type"])

    def test_filter_cases_excludes_pending(self):
        result = self.tools.filter_cases()
        ids = [c["id"] for c in result["results"]]
        if hasattr(self, "pending_case"):
            self.assertNotIn(self.pending_case.id, ids)

    def test_filter_cases_limit(self):
        result = self.tools.filter_cases(limit=1)
        self.assertLessEqual(len(result["results"]), 1)

    def test_filter_cases_offset(self):
        result_all = self.tools.filter_cases(limit=50)
        result_offset = self.tools.filter_cases(limit=50, offset=1)
        if len(result_all["results"]) > 1:
            self.assertEqual(
                result_offset["results"][0]["id"],
                result_all["results"][1]["id"],
            )

    def test_filter_cases_invalid_date(self):
        result = self.tools.filter_cases(date_after="not-a-date")
        self.assertIn("error", result)

    def test_filter_cases_no_results(self):
        result = self.tools.filter_cases(file_number="NONEXISTENT-999/99")
        self.assertIn("message", result)
        self.assertEqual(result["total"], 0)

    def test_filter_cases_result_fields(self):
        result = self.tools.filter_cases()
        if result["results"]:
            case = result["results"][0]
            self.assertIn("id", case)
            self.assertIn("slug", case)
            self.assertIn("file_number", case)
            self.assertIn("date", case)
            self.assertIn("court_name", case)
            self.assertIn("type", case)
            self.assertIn("ecli", case)

    # --- get_case tests ---

    def test_get_case_by_id(self):
        if hasattr(self, "case1"):
            result = self.tools.get_case(case_id=self.case1.id)
            self.assertEqual(result["id"], self.case1.id)
            self.assertIn("content", result)

    def test_get_case_by_slug(self):
        if hasattr(self, "case1"):
            result = self.tools.get_case(slug=self.case1.slug)
            self.assertEqual(result["id"], self.case1.id)

    def test_get_case_not_found(self):
        result = self.tools.get_case(case_id=999999)
        self.assertIn("error", result)

    def test_get_case_no_params(self):
        result = self.tools.get_case()
        self.assertIn("error", result)

    def test_get_case_content_truncation(self):
        if not self.court:
            self.skipTest("No court fixture")
        # Create a case with very long content
        long_content = "x" * 50000
        big_case = Case.objects.create(
            court=self.court,
            file_number="BIG/01",
            content=long_content,
            slug="test-big-case",
            review_status="accepted",
        )
        result = self.tools.get_case(case_id=big_case.id, full_text=False)
        self.assertTrue(result["content_truncated"])
        self.assertLessEqual(len(result["content"]), 31000)

    def test_get_case_full_text(self):
        if not self.court:
            self.skipTest("No court fixture")
        long_content = "x" * 50000
        big_case = Case.objects.create(
            court=self.court,
            file_number="BIG/02",
            content=long_content,
            slug="test-big-case-2",
            review_status="accepted",
        )
        result = self.tools.get_case(case_id=big_case.id, full_text=True)
        self.assertFalse(result["content_truncated"])

    def test_get_case_has_court_info(self):
        if hasattr(self, "case1"):
            result = self.tools.get_case(case_id=self.case1.id)
            self.assertIn("court", result)
            self.assertIn("name", result["court"])
            self.assertIn("slug", result["court"])

    def test_get_case_excludes_pending(self):
        if hasattr(self, "pending_case"):
            result = self.tools.get_case(case_id=self.pending_case.id)
            self.assertIn("error", result)

    # --- search_cases tests ---

    def test_search_cases_returns_dict(self):
        result = self.tools.search_cases(query="test")
        self.assertIsInstance(result, dict)

    def test_search_cases_handles_es_failure(self):
        result = self.tools.search_cases(query="tort law")
        self.assertTrue("results" in result or "error" in result)

    # --- get_case_statistics tests ---

    def test_get_case_statistics_returns_dict(self):
        result = self.tools.get_case_statistics()
        self.assertIsInstance(result, dict)
        self.assertIn("total", result)
        self.assertIn("time_series", result)
        self.assertIn("top_courts", result)

    def test_get_case_statistics_group_by_year(self):
        result = self.tools.get_case_statistics(group_by="year")
        for bucket in result["time_series"]:
            self.assertEqual(len(bucket["date"]), 4)  # YYYY format

    def test_get_case_statistics_with_date_range(self):
        result = self.tools.get_case_statistics(
            date_after="2023-01-01", date_before="2023-12-31"
        )
        self.assertIsInstance(result["total"], int)
