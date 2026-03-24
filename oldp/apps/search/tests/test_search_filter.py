"""Tests for search API validation and error handling."""

from unittest.mock import MagicMock

from django.test import TestCase
from rest_framework.exceptions import ValidationError
from rest_framework.request import Request
from rest_framework.test import APIRequestFactory

from oldp.apps.search.api import SearchFilter, SearchViewMixin
from oldp.apps.search.exceptions import SearchBackendUnavailable
from oldp.apps.search.filters import SearchSchemaFilter


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

    def test_missing_text_error_message_includes_field_name(self):
        request = self._make_request()
        with self.assertRaises(ValidationError) as ctx:
            self.filter.filter_queryset(request, self.queryset, self.view)
        message = ctx.exception.detail["text"]
        self.assertIn("'text'", str(message))

    def test_valid_text_calls_auto_query(self):
        request = self._make_request(text="BGB")
        self.filter.filter_queryset(request, self.queryset, self.view)
        self.queryset.auto_query.assert_called_once_with("BGB")

    def test_q_param_is_accepted_as_alias(self):
        """The 'q' query parameter should work as an alias for 'text'."""
        request = self._make_request(q="BGB Paragraph 8")
        self.filter.filter_queryset(request, self.queryset, self.view)
        self.queryset.auto_query.assert_called_once_with("BGB Paragraph 8")

    def test_text_takes_precedence_over_q(self):
        """When both 'text' and 'q' are provided, 'text' takes precedence."""
        request = self._make_request(text="from text", q="from q")
        self.filter.filter_queryset(request, self.queryset, self.view)
        self.queryset.auto_query.assert_called_once_with("from text")

    def test_q_alone_without_text_does_not_raise(self):
        """Providing only 'q' should not raise a ValidationError."""
        request = self._make_request(q="test query")
        self.filter.filter_queryset(request, self.queryset, self.view)
        self.queryset.auto_query.assert_called_once_with("test query")


class SearchSchemaFilterFacetTest(TestCase):
    """Test that SearchSchemaFilter applies user-specified facet filters."""

    def setUp(self):
        self.factory = APIRequestFactory()

    def _make_filter_and_index(self, facet_model_name="Law", faceted_fields=None):
        """Create a SearchSchemaFilter with a mock search index class."""
        from haystack import indexes

        # Build dynamic index fields
        fields = {
            "text": indexes.CharField(document=True),
            "facet_model_name": indexes.CharField(faceted=True),
        }
        if faceted_fields:
            for name in faceted_fields:
                fields[name] = indexes.CharField(faceted=True)

        mock_index_class = type(
            "MockIndex",
            (),
            {"FACET_MODEL_NAME": facet_model_name, "fields": fields},
        )

        class TestFilter(SearchSchemaFilter):
            search_index_class = mock_index_class

            def get_default_schema_operation_parameters(self):
                return []

        return TestFilter()

    def _make_request(self, **params):
        return Request(self.factory.get("/api/laws/search/", params))

    def _make_chainable_queryset(self):
        qs = MagicMock()
        qs.filter.return_value = qs
        return qs

    def test_always_filters_by_facet_model_name(self):
        """The filter should always apply facet_model_name_exact."""
        f = self._make_filter_and_index(facet_model_name="Law")
        qs = self._make_chainable_queryset()
        request = self._make_request(text="test")

        f.filter_queryset(request, qs, None)

        qs.filter.assert_called_once_with(facet_model_name_exact="Law")

    def test_applies_user_facet_filter(self):
        """User-provided facet parameters should be applied as filters."""
        f = self._make_filter_and_index(
            facet_model_name="Law", faceted_fields=["book_code"]
        )
        qs = self._make_chainable_queryset()
        request = self._make_request(text="test", book_code="BGB")

        f.filter_queryset(request, qs, None)

        calls = qs.filter.call_args_list
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0].kwargs, {"facet_model_name_exact": "Law"})
        self.assertEqual(calls[1].kwargs, {"book_code_exact": "BGB"})

    def test_ignores_empty_facet_parameter(self):
        """Empty facet parameter values should be ignored."""
        f = self._make_filter_and_index(
            facet_model_name="Law", faceted_fields=["book_code"]
        )
        qs = self._make_chainable_queryset()
        request = self._make_request(text="test", book_code="")

        f.filter_queryset(request, qs, None)

        qs.filter.assert_called_once_with(facet_model_name_exact="Law")

    def test_ignores_whitespace_only_facet_parameter(self):
        """Whitespace-only facet parameter values should be ignored."""
        f = self._make_filter_and_index(
            facet_model_name="Law", faceted_fields=["book_code"]
        )
        qs = self._make_chainable_queryset()
        request = self._make_request(text="test", book_code="   ")

        f.filter_queryset(request, qs, None)

        qs.filter.assert_called_once_with(facet_model_name_exact="Law")

    def test_ignores_non_faceted_parameters(self):
        """Query parameters that don't match faceted fields should be ignored."""
        f = self._make_filter_and_index(facet_model_name="Law")
        qs = self._make_chainable_queryset()
        request = self._make_request(text="test", unknown_field="value")

        f.filter_queryset(request, qs, None)

        qs.filter.assert_called_once_with(facet_model_name_exact="Law")

    def test_multiple_facet_filters_applied(self):
        """Multiple facet parameters should all be applied."""
        f = self._make_filter_and_index(
            facet_model_name="Case",
            faceted_fields=["court", "decision_type"],
        )
        qs = self._make_chainable_queryset()
        request = self._make_request(text="test", court="BGH", decision_type="Urteil")

        f.filter_queryset(request, qs, None)

        calls = qs.filter.call_args_list
        self.assertEqual(len(calls), 3)
        filter_kwargs = [c.kwargs for c in calls]
        self.assertIn({"facet_model_name_exact": "Case"}, filter_kwargs)
        self.assertIn({"court_exact": "BGH"}, filter_kwargs)
        self.assertIn({"decision_type_exact": "Urteil"}, filter_kwargs)


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
