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
class SearchApiMockedTestCase(TestCase):
    """Tests for search API with fully mocked SearchQuerySet."""

    def _make_mock_sqs(self, results=None):
        mock_sqs = MagicMock()
        mock_sqs.models.return_value = mock_sqs
        mock_sqs.filter.return_value = mock_sqs
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
