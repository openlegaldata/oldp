from unittest.mock import MagicMock, patch

from django.core.cache import cache
from django.test import TestCase, override_settings


def _make_mock_search_sqs():
    mock_sqs = MagicMock()
    mock_sqs.models.return_value = mock_sqs
    mock_sqs.filter.return_value = mock_sqs
    mock_sqs.auto_query.return_value = mock_sqs
    mock_sqs.__len__ = MagicMock(return_value=0)
    mock_sqs.__iter__ = MagicMock(return_value=iter([]))
    mock_sqs.__getitem__ = MagicMock(return_value=[])
    mock_sqs.count.return_value = 0
    return mock_sqs


@override_settings(
    CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "search-api-cache-tests",
        }
    }
)
class SearchApiCacheHeadersTestCase(TestCase):
    def _assert_cached_vary_headers(self, response):
        self.assertEqual(200, response.status_code)
        vary = response.get("Vary", "")
        self.assertIn("Authorization", vary)
        self.assertIn("Cookie", vary)
        self.assertIn("Accept-Language", vary)
        self.assertIn("Host", vary)
        self.assertIn("max-age", response.get("Cache-Control", ""))

    @patch("oldp.apps.search.api.SearchQuerySet")
    def test_law_search_api_is_cached_with_vary_headers(self, mock_sqs_cls):
        cache.clear()
        mock_sqs_cls.return_value = _make_mock_search_sqs()

        url = "/api/laws/search/?text=gg"
        res1 = self.client.get(url)
        res2 = self.client.get(url)

        self._assert_cached_vary_headers(res1)
        self._assert_cached_vary_headers(res2)
        self.assertEqual(1, mock_sqs_cls.call_count)
        cache.clear()

    @patch("oldp.apps.search.api.SearchQuerySet")
    def test_case_search_api_is_cached_with_vary_headers(self, mock_sqs_cls):
        cache.clear()
        mock_sqs_cls.return_value = _make_mock_search_sqs()

        url = "/api/cases/search/?text=gericht"
        res1 = self.client.get(url)
        res2 = self.client.get(url)

        self._assert_cached_vary_headers(res1)
        self._assert_cached_vary_headers(res2)
        self.assertEqual(1, mock_sqs_cls.call_count)
        cache.clear()
