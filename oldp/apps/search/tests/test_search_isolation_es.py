"""Real-ES regression tests for MCP search-tool model isolation.

Pins the contract that `search_laws` and `search_cases` constrain results
to their respective Elasticsearch indexes. The custom SearchBackend
silently drops Haystack's `.models()` filter against real ES, so without
the `facet_model_name_exact` guard a query without a `book_code` filter
would leak case results out of the law search tool.

The default `MOCK_ES_TESTS=True` mock backend honors `.models()` correctly,
so these tests only run against real Elasticsearch (CI `test-es` job).
"""

from django.test import TestCase, override_settings

from oldp.apps.cases.mcp import CaseTools
from oldp.apps.laws.mcp import LawTools
from oldp.apps.laws.models import Law, LawBook
from oldp.utils.test_utils import ElasticsearchTestMixin, real_es_test


@override_settings(
    CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "search-isolation-tests",
        }
    },
)
class SearchModelIsolationRealESTest(ElasticsearchTestMixin, TestCase):
    """Verifies search_laws / search_cases never leak across model boundaries.

    Indexes both Law and Case fixtures into a real ES cluster and queries
    for a term ("Satz") that appears in *both* the Grundgesetz law text
    (75+ matches) and the dummy case content (case 1: "In diesem Satz
    sind Zitate ..."). Pre-fix, `search_laws("Satz")` would return Case
    documents alongside Laws; post-fix, the `facet_model_name_exact`
    filter constrains each tool to its model.
    """

    fixtures = [
        "locations/countries.json",
        "locations/states.json",
        "locations/cities.json",
        "courts/courts.json",
        "laws/laws.json",
        "cases/cases.json",
    ]

    # A term known to occur in both the Grundgesetz fixture (~75 sections
    # mention "Satz") and the dummy case content (case 1: "In diesem
    # Satz sind Zitate ..."). Picked deliberately so the search would
    # match both indexes if model isolation broke.
    SHARED_QUERY = "Satz"

    def setUp(self):
        super().setUp()
        self.index_fixtures()
        self.law_tools = LawTools()
        self.case_tools = CaseTools()

    @real_es_test
    def test_search_laws_returns_only_law_documents(self):
        result = self.law_tools.search_laws(query=self.SHARED_QUERY, limit=50)
        self.assertIn("results", result, msg=result)

        # Sanity check: the indexed fixture data must contain at least
        # one Law match for the shared term. If this fails the test
        # fixture changed and the assertion below would pass vacuously.
        self.assertGreaterEqual(
            result.get("total", 0),
            1,
            msg=(
                "Fixture sanity: expected the Grundgesetz fixture to "
                "contain at least one section matching 'Satz'."
            ),
        )

        # Every entry must carry a non-empty book_code. Laws have it via
        # LawIndex.prepare_book_code; Case documents have no book_code
        # field and would surface here as empty strings (the bug pre-fix).
        for entry in result["results"]:
            self.assertTrue(
                entry.get("book_code"),
                msg=(
                    "search_laws leaked a non-Law document: "
                    f"{entry!r}. The facet_model_name_exact='Law' filter is "
                    "missing or being dropped by the search backend."
                ),
            )

    @real_es_test
    def test_search_laws_matches_section_title(self):
        """Regression test.

        Section titles like "Notwehr" (§ 32 StGB) must be searchable.
        Pre-fix the LawIndex template rendered only the law body via
        `{{ object.get_text }}`, so a query for a title-only term
        returned zero matches even though the `title` field held it.
        After adding title/amtabk/kurzue to the template, the title is
        part of the analyzed text and matches the query.

        Construct a Law whose title contains a unique token that is
        guaranteed not to appear in any other law's body text or in the
        case fixtures, then assert that searching for it returns the
        section. This isolates the title-indexing behaviour from the
        rest of the fixture data.
        """
        unique_title_token = "QqqUniqueTitleTokenZzz"
        book = LawBook.objects.create(
            code="TITLETEST",
            title="Title-indexing regression book",
            slug="titletest",
            latest=True,
            review_status="accepted",
        )
        Law.objects.create(
            book=book,
            section="§ 1",
            title=f"Some title with the {unique_title_token} word",
            slug="1",
            content="<p>This body does not contain the magic token.</p>",
            review_status="accepted",
        )
        # Re-index now that the new Law exists; the setUp call ran before
        # this method created its data.
        self.index_fixtures(models=[Law])

        result = self.law_tools.search_laws(query=unique_title_token, limit=5)
        self.assertIn("results", result, msg=result)
        self.assertGreaterEqual(
            result.get("total", 0),
            1,
            msg=(
                f"Expected to find a law via its title-only token "
                f"{unique_title_token!r}. If this fails, the title "
                "is still not part of the indexed text field — "
                "re-check oldp/apps/search/templates/search/indexes/"
                "laws/law_text.txt."
            ),
        )

    @real_es_test
    def test_search_cases_returns_only_case_documents(self):
        result = self.case_tools.search_cases(query=self.SHARED_QUERY, limit=50)
        self.assertIn("results", result, msg=result)

        # Cases have a `date` and a `court` field, laws don't. Pre-fix a
        # leaked Law would surface with an empty date/court.
        for entry in result["results"]:
            self.assertTrue(
                entry.get("court"),
                msg=(
                    "search_cases leaked a non-Case document: "
                    f"{entry!r}. The facet_model_name_exact='Case' filter is "
                    "missing or being dropped by the search backend."
                ),
            )
