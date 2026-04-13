"""Unit tests for law MCP tools."""

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
