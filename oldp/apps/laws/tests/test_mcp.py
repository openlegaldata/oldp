"""Unit tests for law MCP tools."""

from unittest.mock import patch

from django.test import TestCase, override_settings

from oldp.apps.laws.mcp import LawTools
from oldp.apps.laws.models import Law, LawBook


@override_settings(
    CACHES={"default": {"BACKEND": "django.core.cache.backends.dummy.DummyCache"}}
)
class LawToolsTests(TestCase):
    """Tests for list_law_books, get_law_section, and search_laws MCP tools."""

    fixtures = [
        "locations/countries.json",
        "locations/states.json",
        "locations/cities.json",
        "courts/courts.json",
        "laws/laws.json",
    ]

    def setUp(self):
        self.tools = LawTools()

    # --- list_law_books tests ---

    def test_list_law_books_returns_results(self):
        result = self.tools.list_law_books()
        self.assertIn("results", result)
        self.assertIsInstance(result["results"], list)

    def test_list_law_books_result_fields(self):
        result = self.tools.list_law_books()
        if result["results"]:
            book = result["results"][0]
            self.assertIn("id", book)
            self.assertIn("code", book)
            self.assertIn("title", book)
            self.assertIn("section_count", book)

    def test_list_law_books_latest_only(self):
        result = self.tools.list_law_books(latest_only=True)
        for book in result.get("results", []):
            self.assertTrue(book["latest"])

    def test_list_law_books_search(self):
        book = LawBook.objects.filter(latest=True, review_status="accepted").first()
        if book:
            result = self.tools.list_law_books(search=book.code)
            self.assertTrue(any(b["code"] == book.code for b in result["results"]))

    def test_list_law_books_limit(self):
        result = self.tools.list_law_books(limit=2)
        self.assertLessEqual(len(result["results"]), 2)

    def test_list_law_books_no_results_message(self):
        result = self.tools.list_law_books(search="zzz_nonexistent_zzz")
        self.assertIn("message", result)

    # --- get_law_section tests ---

    def test_get_law_section_by_book_and_section(self):
        law = (
            Law.objects.filter(review_status="accepted", book__latest=True)
            .select_related("book")
            .first()
        )
        if law:
            result = self.tools.get_law_section(
                book_code=law.book.code, section=law.section
            )
            self.assertEqual(result["id"], law.id)
            self.assertIn("content", result)

    def test_get_law_section_by_id(self):
        law = Law.objects.filter(review_status="accepted", book__latest=True).first()
        if law:
            result = self.tools.get_law_section(law_id=law.id)
            self.assertEqual(result["id"], law.id)
            self.assertIn("content", result)

    def test_get_law_section_not_found(self):
        result = self.tools.get_law_section(book_code="BGB", section="999999")
        self.assertIn("error", result)

    def test_get_law_section_invalid_book(self):
        result = self.tools.get_law_section(book_code="NONEXISTENT", section="1")
        self.assertIn("error", result)

    def test_get_law_section_no_params(self):
        result = self.tools.get_law_section()
        self.assertIn("error", result)

    def test_get_law_section_fields(self):
        law = (
            Law.objects.filter(review_status="accepted", book__latest=True)
            .select_related("book")
            .first()
        )
        if law:
            result = self.tools.get_law_section(law_id=law.id)
            self.assertIn("book_code", result)
            self.assertIn("book_title", result)
            self.assertIn("section", result)
            self.assertIn("title", result)
            self.assertIn("slug", result)

    # --- search_laws tests ---

    def test_search_laws_returns_dict(self):
        result = self.tools.search_laws(query="test")
        self.assertIsInstance(result, dict)

    def test_search_laws_handles_es_failure_gracefully(self):
        # With mock ES, this should return results or a graceful error
        result = self.tools.search_laws(query="Recht")
        self.assertTrue("results" in result or "error" in result)

    def _patched_search_laws(self, **kwargs):
        """Run search_laws against a fake queryset and return (result, filters).

        The fake records every .filter(**kwargs) call so tests can assert on
        which filters were applied to the SearchQuerySet chain.
        """

        class FakeSearchQuerySet:
            def __init__(self):
                self.filters = []

            def auto_query(self, query):
                return self

            def filter(self, **kwargs):
                self.filters.append(kwargs)
                return self

            def __getitem__(self, key):
                return []

        class FakeSearchQueryBuilder:
            def __init__(self):
                self.sqs = FakeSearchQuerySet()

            def filter_models(self, models):
                return self

            def filter_review_status(self, status):
                return self

            def apply_highlight(self):
                return self

            def build(self):
                return self.sqs

        builder = FakeSearchQueryBuilder()
        with patch("oldp.apps.search.api.SearchQueryBuilder", return_value=builder):
            result = self.tools.search_laws(**kwargs)
        return result, builder.sqs.filters

    def test_search_laws_uses_exact_book_code_filter(self):
        result, filters = self._patched_search_laws(query="test", book_code="bgb")
        self.assertEqual(result["total"], 0)
        self.assertIn({"book_code_exact": "BGB"}, filters)

    def test_search_laws_always_constrains_to_law_index(self):
        """Regression: docs/mcp-test-report.md issue #1.

        search_laws must filter on facet_model_name_exact="Law" regardless
        of whether book_code is set, otherwise the custom SearchBackend
        silently lets case-shaped results leak into law search responses.
        """
        # No book_code -> the bug-prone path.
        _, filters_no_book = self._patched_search_laws(query="test")
        self.assertIn({"facet_model_name_exact": "Law"}, filters_no_book)

        # With book_code -> filter is still applied (belt-and-suspenders).
        _, filters_with_book = self._patched_search_laws(query="test", book_code="BGB")
        self.assertIn({"facet_model_name_exact": "Law"}, filters_with_book)
        self.assertIn({"book_code_exact": "BGB"}, filters_with_book)
