"""Tests for search API validation and error handling."""

from unittest.mock import MagicMock, patch

from django.test import TestCase
from rest_framework.exceptions import ValidationError
from rest_framework.request import Request
from rest_framework.test import APIRequestFactory

from oldp.apps.search.api import SearchFilter, SearchViewMixin
from oldp.apps.search.exceptions import SearchBackendUnavailable


class SearchFilterValidationTest(TestCase):
    """Test that SearchFilter enforces the required 'text' parameter."""

    def setUp(self):
        self.factory = APIRequestFactory()
        self.filter = SearchFilter()
        self.queryset = MagicMock()
        self.view = MagicMock(search_models=[])

    def _make_request(self, **params):
        """Create a DRF Request with query params."""
        return Request(self.factory.get("/api/cases/search/", params))

    def test_missing_text_returns_400(self):
        request = self._make_request()
        with self.assertRaises(ValidationError) as ctx:
            self.filter.filter_queryset(request, self.queryset, self.view)
        self.assertIn("text", ctx.exception.detail)

    def test_empty_text_returns_400(self):
        request = self._make_request(text="")
        with self.assertRaises(ValidationError):
            self.filter.filter_queryset(request, self.queryset, self.view)

    def test_whitespace_only_text_returns_400(self):
        request = self._make_request(text="   ")
        with self.assertRaises(ValidationError):
            self.filter.filter_queryset(request, self.queryset, self.view)

    def test_valid_text_calls_auto_query(self):
        request = self._make_request(text="BGB")
        self.filter.filter_queryset(request, self.queryset, self.view)
        self.queryset.auto_query.assert_called_once_with("BGB")


class SearchViewMixinErrorHandlingTest(TestCase):
    """Test that SearchViewMixin catches Elasticsearch connection errors."""

    def setUp(self):
        self.factory = APIRequestFactory()

    def test_elasticsearch_connection_error_returns_503(self):
        try:
            from elasticsearch.exceptions import ConnectionError as ESConnectionError
        except ImportError:
            self.skipTest("elasticsearch package not installed")

        class FakeParent:
            def list(self, request, *args, **kwargs):
                raise ESConnectionError("ES down")

        class TestView(SearchViewMixin, FakeParent):
            pass

        view = TestView()
        request = Request(self.factory.get("/api/cases/search/", {"text": "test"}))
        with self.assertRaises(SearchBackendUnavailable):
            view.list(request)

    def test_non_es_exception_propagates(self):
        class FakeParent:
            def list(self, request, *args, **kwargs):
                raise ValueError("other error")

        class TestView(SearchViewMixin, FakeParent):
            pass

        view = TestView()
        request = Request(self.factory.get("/api/cases/search/", {"text": "test"}))
        with self.assertRaises(ValueError):
            view.list(request)
