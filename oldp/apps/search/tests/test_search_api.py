"""Integration tests for search API with Elasticsearch (mock and real)."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.test import TestCase, override_settings

from oldp.utils.test_utils import ElasticsearchTestMixin, es_test, real_es_test


@override_settings(
    CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "search-api-integration-tests",
        }
    },
    STORAGES={
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
        }
    },
)
class SearchApiIntegrationTestCase(ElasticsearchTestMixin, TestCase):
    """Integration tests for search API endpoints with ES backend."""

    fixtures = [
        "locations/countries.json",
        "locations/states.json",
        "locations/cities.json",
        "courts/courts.json",
        "cases/cases.json",
    ]

    def setUp(self):
        super().setUp()
        self.index_fixtures()

    @es_test
    def test_case_search_returns_snippets(self):
        """API search should return snippets list instead of full text."""
        res = self.client.get("/api/cases/search/?text=test")
        self.assertEqual(200, res.status_code)
        data = res.json()
        if data["count"] > 0:
            result = data["results"][0]
            self.assertIn("snippets", result)
            self.assertNotIn("text", result)

    @es_test
    def test_case_search_snippet_structure(self):
        """Each snippet should have text, offset, and length keys."""
        res = self.client.get("/api/cases/search/?text=test")
        self.assertEqual(200, res.status_code)
        data = res.json()
        if data["count"] > 0:
            snippet = data["results"][0]["snippets"][0]
            self.assertIn("text", snippet)
            self.assertIn("offset", snippet)
            self.assertIn("length", snippet)
            self.assertIsInstance(snippet["offset"], int)
            self.assertIsInstance(snippet["length"], int)

    @es_test
    def test_case_search_return_text_includes_full_text(self):
        """With return_text=1, response should include both text and snippets."""
        res = self.client.get("/api/cases/search/?text=test&return_text=1")
        self.assertEqual(200, res.status_code)
        data = res.json()
        if data["count"] > 0:
            result = data["results"][0]
            self.assertIn("text", result)
            self.assertIn("snippets", result)

    @es_test
    def test_case_search_missing_text_returns_400(self):
        """Missing text parameter should return 400."""
        res = self.client.get("/api/cases/search/")
        self.assertEqual(400, res.status_code)

    @es_test
    def test_law_search_returns_snippets(self):
        """Law search API should also return snippets."""
        res = self.client.get("/api/laws/search/?text=test")
        self.assertEqual(200, res.status_code)
        data = res.json()
        if data["count"] > 0:
            result = data["results"][0]
            self.assertIn("snippets", result)

    @real_es_test
    def test_real_es_highlighting_returns_em_tags(self):
        """With real ES, highlighted snippets should contain <em> tags."""
        res = self.client.get("/api/cases/search/?text=test")
        self.assertEqual(200, res.status_code)
        data = res.json()
        if data["count"] > 0:
            snippets = data["results"][0]["snippets"]
            # At least one snippet should have highlighting tags
            has_em = any("<em>" in s["text"] for s in snippets)
            self.assertTrue(has_em, "Expected <em> tags in highlighted snippets")

    @real_es_test
    @override_settings(SEARCH_MAX_SNIPPETS=3)
    def test_real_es_multiple_snippets(self):
        """With real ES, multiple snippets should be returned."""
        res = self.client.get("/api/cases/search/?text=test")
        self.assertEqual(200, res.status_code)
        data = res.json()
        if data["count"] > 0:
            snippets = data["results"][0]["snippets"]
            # Should have at least 1 snippet (may have more depending on content)
            self.assertGreaterEqual(len(snippets), 1)

    @real_es_test
    def test_real_es_snippet_offset_matches_text(self):
        """With real ES, snippet offset should point to correct position in text."""
        res = self.client.get("/api/cases/search/?text=test&return_text=1")
        self.assertEqual(200, res.status_code)
        data = res.json()
        if data["count"] > 0:
            result = data["results"][0]
            full_text = result.get("text", "")
            for snippet in result["snippets"]:
                if snippet["offset"] >= 0 and full_text:
                    # Strip tags and verify offset
                    import re

                    plain = re.sub(r"</?em>", "", snippet["text"])
                    actual = full_text[
                        snippet["offset"] : snippet["offset"] + len(plain)
                    ]
                    self.assertEqual(actual, plain)


@override_settings(
    CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "search-api-mock-tests",
        }
    },
)
class CaseSearchSerializerCourtTestCase(TestCase):
    """``CaseSearchSerializer`` must normalize the placeholder "unknown"
    court code to null — parity with the MCP ``search_cases`` tool, so REST
    consumers never mistake the ingestion-artefact "unknown" for a real
    court (audit A4 / #10).
    """

    def _court_of(self, code):
        from oldp.apps.cases.serializers import CaseSearchSerializer

        result = SimpleNamespace(
            text="t", title="T", slug="s", pk="1", court=code, citing_cases_count=0
        )
        return CaseSearchSerializer().to_representation(result)["court"]

    def test_unknown_becomes_null(self):
        self.assertIsNone(self._court_of("unknown"))
        self.assertIsNone(self._court_of("Unknown"))

    def test_real_court_passes_through(self):
        self.assertEqual(self._court_of("BGH"), "BGH")
        self.assertEqual(self._court_of("VERFGBE"), "VERFGBE")


class SearchApiMockedTestCase(TestCase):
    """Tests for search API with fully mocked SearchQuerySet."""

    def _make_mock_sqs(self, results=None):
        mock_sqs = MagicMock()
        mock_sqs.models.return_value = mock_sqs
        mock_sqs.filter.return_value = mock_sqs
        mock_sqs.narrow.return_value = mock_sqs
        mock_sqs.auto_query.return_value = mock_sqs
        mock_sqs.highlight.return_value = mock_sqs

        results = results or []
        mock_sqs.__len__ = MagicMock(return_value=len(results))
        mock_sqs.__iter__ = MagicMock(return_value=iter(results))
        mock_sqs.__getitem__ = MagicMock(return_value=results)
        mock_sqs.count.return_value = len(results)
        return mock_sqs

    def _make_search_result(self, text="Sample text", highlighted=None):
        attrs = {
            "text": text,
            "title": "Test",
            "slug": "test",
            "pk": "1",
            "book_code": "BGB",
        }
        if highlighted is not None:
            attrs["highlighted"] = highlighted
        return SimpleNamespace(**attrs)

    @patch("oldp.apps.search.api.SearchQuerySet")
    def test_law_search_snippets_in_response(self, mock_sqs_cls):
        result = self._make_search_result(
            text="Long legal text about BGB", highlighted=["legal <em>text</em>"]
        )
        mock_sqs_cls.return_value = self._make_mock_sqs([result])

        res = self.client.get("/api/laws/search/?text=BGB")
        self.assertEqual(200, res.status_code)
        data = res.json()
        self.assertEqual(data["count"], 1)
        self.assertIn("snippets", data["results"][0])
        self.assertNotIn("text", data["results"][0])

    @patch("oldp.apps.search.api.SearchQuerySet")
    def test_law_search_return_text_param(self, mock_sqs_cls):
        result = self._make_search_result(
            text="Full text here", highlighted=["<em>Full</em> text"]
        )
        mock_sqs_cls.return_value = self._make_mock_sqs([result])

        res = self.client.get("/api/laws/search/?text=test&return_text=1")
        self.assertEqual(200, res.status_code)
        data = res.json()
        self.assertIn("text", data["results"][0])
        self.assertIn("snippets", data["results"][0])
        self.assertEqual(data["results"][0]["text"], "Full text here")

    @patch("oldp.apps.search.api.SearchQuerySet")
    def test_date_range_params_accepted(self, mock_sqs_cls):
        mock_sqs_cls.return_value = self._make_mock_sqs()

        res = self.client.get(
            "/api/cases/search/?text=test&start_date=2020-01-01&end_date=2024-12-31"
        )
        self.assertEqual(200, res.status_code)

    @patch("oldp.apps.search.api.SearchQuerySet")
    def test_case_search_chains_law_citation_filter(self, mock_sqs_cls):
        """``cited_law_book`` + ``cited_law_section`` should chain a
        ``cited_laws=<token>`` filter and the Case clamp onto the
        keyword query.
        """
        mock_sqs = self._make_mock_sqs()
        mock_sqs_cls.return_value = mock_sqs

        res = self.client.get(
            "/api/cases/search/?text=mietrecht&cited_law_book=bgb&cited_law_section=823"
        )
        self.assertEqual(200, res.status_code)

        filter_calls = [c.kwargs for c in mock_sqs.filter.call_args_list]
        self.assertIn({"cited_laws": "bgb__823"}, filter_calls)
        self.assertIn({"facet_model_name_exact": "Case"}, filter_calls)

    @patch("oldp.apps.search.api.SearchQuerySet")
    def test_case_search_chains_case_citation_filter(self, mock_sqs_cls):
        mock_sqs = self._make_mock_sqs()
        mock_sqs_cls.return_value = mock_sqs

        res = self.client.get("/api/cases/search/?text=foo&cited_case=42")
        self.assertEqual(200, res.status_code)

        filter_calls = [c.kwargs for c in mock_sqs.filter.call_args_list]
        self.assertIn({"cited_cases": "42"}, filter_calls)

    @patch("oldp.apps.search.api.SearchQuerySet")
    def test_law_search_ignores_citation_filter(self, mock_sqs_cls):
        """Citation fields aren't populated on the Law index — silently
        ignore citation params on ``/api/laws/search/`` rather than
        clamping to Case and returning empty.
        """
        mock_sqs = self._make_mock_sqs()
        mock_sqs_cls.return_value = mock_sqs

        res = self.client.get(
            "/api/laws/search/?text=foo&cited_law_book=bgb&cited_law_section=823"
        )
        self.assertEqual(200, res.status_code)

        filter_calls = [c.kwargs for c in mock_sqs.filter.call_args_list]
        self.assertNotIn({"cited_laws": "bgb__823"}, filter_calls)

    def test_schema_lists_citation_params(self):
        """The OpenAPI schema for ``SearchFilter`` should declare the
        three citation params so REST docs surface them.
        """
        from oldp.apps.search.api import SearchFilter

        params = SearchFilter().get_schema_operation_parameters(view=None)
        names = {p["name"] for p in params}
        self.assertIn("cited_law_book", names)
        self.assertIn("cited_law_section", names)
        self.assertIn("cited_case", names)
