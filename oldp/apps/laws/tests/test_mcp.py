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

    def test_get_law_section_content_is_plain_text(self):
        law = Law.objects.filter(review_status="accepted", book__latest=True).first()
        if not law:
            self.skipTest("No law fixture")
        law.content = (
            "<P>(1) <SUP class='Rec'>1</SUP>Es gilt <DL><DT>1.</DT>"
            "<DD><LA>erstens,</LA></DD><DT>2.</DT><DD><LA>zweitens.</LA></DD></DL></P>"
        )
        law.save()
        result = self.tools.get_law_section(law_id=law.id)
        self.assertEqual(result["content"], "(1) 1 Es gilt\n1. erstens,\n2. zweitens.")

    def test_get_law_section_snippet(self):
        law = Law.objects.filter(review_status="accepted", book__latest=True).first()
        if not law:
            self.skipTest("No law fixture")
        result = self.tools.get_law_section(law_id=law.id, length=10)
        self.assertNotIn("content", result)
        snippet = result["snippet"]
        self.assertLessEqual(snippet["length"], 10)
        self.assertNotIn("<", snippet["text"])
        self.assertEqual(snippet["offset"], 0)

    def test_get_law_section_snippet_invalid_offset(self):
        law = Law.objects.filter(review_status="accepted", book__latest=True).first()
        if not law:
            self.skipTest("No law fixture")
        result = self.tools.get_law_section(law_id=law.id, offset=-1)
        self.assertIn("error", result)

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
                self.narrows = []

            def auto_query(self, query):
                return self

            def filter(self, **kwargs):
                self.filters.append(kwargs)
                return self

            def narrow(self, query):
                self.narrows.append(query)
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
        self._last_narrows = builder.sqs.narrows
        return result, builder.sqs.filters

    def test_search_laws_uses_exact_book_code_filter(self):
        result, filters = self._patched_search_laws(query="test", book_code="bgb")
        self.assertEqual(result["total"], 0)
        self.assertIn({"book_code_exact": "BGB"}, filters)

    def test_search_laws_always_constrains_to_law_index(self):
        """Regression test.

        search_laws must clamp to facet_model_name_exact="Law" regardless of
        whether book_code is set, otherwise the custom SearchBackend silently
        lets case-shaped results leak into law search responses. The clamp is
        a filter-context narrow (not a scoring .filter) so a navigational
        lookup ("bgb 123") still ranks the on-point law #1.
        """
        # No book_code -> the bug-prone path.
        self._patched_search_laws(query="test")
        self.assertIn('facet_model_name_exact:"Law"', self._last_narrows)

        # With book_code -> clamp is still applied (belt-and-suspenders).
        _, filters_with_book = self._patched_search_laws(query="test", book_code="BGB")
        self.assertIn('facet_model_name_exact:"Law"', self._last_narrows)
        self.assertIn({"book_code_exact": "BGB"}, filters_with_book)


@override_settings(
    CACHES={"default": {"BACKEND": "django.core.cache.backends.dummy.DummyCache"}}
)
class LawSectionLookupTests(TestCase):
    """get_law_section resolves every prefix spelling, but only exact sections.

    Article-based books store their labels in different spellings depending
    on the source ("Art 20", "Art. 6", "Artikel 1"). The lookup used to try
    the input verbatim and then a substring match, so "Art. 20" and
    "Artikel 20" missed "Art 20", and a bare number could land on a longer
    section that contains it.
    """

    def setUp(self):
        self.tools = LawTools()

    def _book(self, code, sections):
        book = LawBook.objects.create(
            code=code,
            title=f"{code} test book",
            slug=code.lower(),
            latest=True,
            review_status="accepted",
        )
        for order, section in enumerate(sections, start=1):
            Law.objects.create(
                book=book,
                section=section,
                title=section,
                slug=f"{code.lower()}-{order}",
                order=order,
                content=f"<p>{section}</p>",
                review_status="accepted",
            )
        return book

    def assertResolves(self, code, section, expected):
        result = self.tools.get_law_section(book_code=code, section=section)
        self.assertNotIn("error", result, msg=f"{code} {section!r}: {result}")
        self.assertEqual(result["section"], expected, msg=f"{code} {section!r}")

    def test_article_spellings_resolve_for_each_storage_form(self):
        self._book("ARTNODOT", ["Art 1", "Art 20", "Art 20a", "Art 120"])
        self._book("ARTDOT", ["Art. 5", "Art. 6", "Art. 16"])
        self._book("ARTLONG", ["Artikel 1", "Artikel 2"])
        for code, number, stored in [
            ("ARTNODOT", "20", "Art 20"),
            ("ARTDOT", "6", "Art. 6"),
            ("ARTLONG", "2", "Artikel 2"),
        ]:
            for section in [
                number,
                f"Art {number}",
                f"Art. {number}",
                f"Artikel {number}",
                f"art.{number}",
                f"  Art.  {number} ",
            ]:
                with self.subTest(code=code, section=section):
                    self.assertResolves(code, section, stored)

    def test_paragraph_spellings_resolve(self):
        self._book("PARA", ["§ 1", "§ 823", "§ 1823", "§ 8230"])
        for section in ["823", "§ 823", "§823", "§§ 823"]:
            with self.subTest(section=section):
                self.assertResolves("PARA", section, "§ 823")

    def test_no_substring_match(self):
        """A missing section must not resolve to a longer one containing it."""
        self._book("SUBSTR", ["§ 1823", "Art 120", "§§ 3 bis 6"])
        for section in ["823", "§ 823", "20", "Art. 20", "3"]:
            with self.subTest(section=section):
                result = self.tools.get_law_section(book_code="SUBSTR", section=section)
                self.assertIn("error", result)

    def test_letter_suffix_is_distinct(self):
        self._book("SUFFIX", ["Art 20", "Art 20a"])
        self.assertResolves("SUFFIX", "Art. 20a", "Art 20a")
        self.assertResolves("SUFFIX", "20", "Art 20")

    def test_non_numeric_labels_resolve_verbatim(self):
        self._book("LABELS", ["Eingangsformel", "Anlage 1"])
        self.assertResolves("LABELS", "Eingangsformel", "Eingangsformel")
        self.assertResolves("LABELS", "anlage 1", "Anlage 1")

    def test_not_found_hint_shows_stored_labels(self):
        self._book("HINTED", ["Art 1", "Art 2", "Art 3", "Art 4"])
        result = self.tools.get_law_section(book_code="HINTED", section="Art. 99")
        self.assertIn("error", result)
        self.assertIn("'Art 1', 'Art 2', 'Art 3'", result["hint"])
        self.assertIn("search_laws", result["hint"])
