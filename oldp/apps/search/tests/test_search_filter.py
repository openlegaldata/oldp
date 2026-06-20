"""Tests for search API validation, error handling, query building, and snippets."""

from unittest.mock import MagicMock, patch

from django.test import TestCase, override_settings
from rest_framework.exceptions import ValidationError
from rest_framework.request import Request
from rest_framework.test import APIRequestFactory

from oldp.apps.search.api import (
    SearchFilter,
    SearchQueryBuilder,
    SearchResultSerializer,
    SearchViewMixin,
    _build_snippets,
    _strip_highlight_tags,
)
from oldp.apps.search.exceptions import SearchBackendUnavailable
from oldp.apps.search.filters import SearchSchemaFilter


class SearchFilterSortTest(TestCase):
    """REST `order_by` (relevance|date|most_cited), parity with web/MCP."""

    def setUp(self):
        self.factory = APIRequestFactory()
        self.filter = SearchFilter()
        # Self-chaining queryset so we can inspect order_by calls.
        self.qs = MagicMock()
        for m in ("auto_query", "models", "filter", "order_by"):
            getattr(self.qs, m).return_value = self.qs
        self.view = MagicMock(search_models=[])

    def _run(self, **params):
        params.setdefault("text", "BGB")
        req = Request(self.factory.get("/api/cases/search/", params))
        self.filter.filter_queryset(req, self.qs, self.view)

    def test_default_relevance_does_not_order(self):
        self._run()
        self.qs.order_by.assert_not_called()

    def test_order_by_date(self):
        self._run(order_by="date")
        self.qs.order_by.assert_any_call("-date")

    def test_order_by_most_cited(self):
        self._run(order_by="most_cited")
        self.qs.order_by.assert_any_call("-citing_cases_count")

    def test_unknown_order_by_ignored(self):
        self._run(order_by="bogus")
        self.qs.order_by.assert_not_called()


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
        qs.narrow.return_value = qs
        return qs

    def test_always_filters_by_facet_model_name(self):
        """The model clamp is applied as a filter-context narrow (not a
        scoring .filter) so short navigational lookups stay eligible for the
        exact-match boost. See ``narrow_to_model``.
        """
        f = self._make_filter_and_index(facet_model_name="Law")
        qs = self._make_chainable_queryset()
        request = self._make_request(text="test")

        f.filter_queryset(request, qs, None)

        qs.narrow.assert_called_once_with('facet_model_name_exact:"Law"')
        qs.filter.assert_not_called()

    def test_applies_user_facet_filter(self):
        """User-provided facet parameters should be applied as filters.

        The model clamp goes through ``.narrow`` (filter context); the
        user-supplied facet stays a scoring ``.filter``.
        """
        f = self._make_filter_and_index(
            facet_model_name="Law", faceted_fields=["book_code"]
        )
        qs = self._make_chainable_queryset()
        request = self._make_request(text="test", book_code="BGB")

        f.filter_queryset(request, qs, None)

        qs.narrow.assert_called_once_with('facet_model_name_exact:"Law"')
        qs.filter.assert_called_once_with(book_code_exact="BGB")

    def test_ignores_empty_facet_parameter(self):
        """Empty facet parameter values should be ignored."""
        f = self._make_filter_and_index(
            facet_model_name="Law", faceted_fields=["book_code"]
        )
        qs = self._make_chainable_queryset()
        request = self._make_request(text="test", book_code="")

        f.filter_queryset(request, qs, None)

        qs.narrow.assert_called_once_with('facet_model_name_exact:"Law"')
        qs.filter.assert_not_called()

    def test_ignores_whitespace_only_facet_parameter(self):
        """Whitespace-only facet parameter values should be ignored."""
        f = self._make_filter_and_index(
            facet_model_name="Law", faceted_fields=["book_code"]
        )
        qs = self._make_chainable_queryset()
        request = self._make_request(text="test", book_code="   ")

        f.filter_queryset(request, qs, None)

        qs.narrow.assert_called_once_with('facet_model_name_exact:"Law"')
        qs.filter.assert_not_called()

    def test_ignores_non_faceted_parameters(self):
        """Query parameters that don't match faceted fields should be ignored."""
        f = self._make_filter_and_index(facet_model_name="Law")
        qs = self._make_chainable_queryset()
        request = self._make_request(text="test", unknown_field="value")

        f.filter_queryset(request, qs, None)

        qs.narrow.assert_called_once_with('facet_model_name_exact:"Law"')
        qs.filter.assert_not_called()

    def test_multiple_facet_filters_applied(self):
        """Multiple facet parameters should all be applied (model clamp via
        narrow, user facets via filter).
        """
        f = self._make_filter_and_index(
            facet_model_name="Case",
            faceted_fields=["court", "decision_type"],
        )
        qs = self._make_chainable_queryset()
        request = self._make_request(text="test", court="BGH", decision_type="Urteil")

        f.filter_queryset(request, qs, None)

        qs.narrow.assert_called_once_with('facet_model_name_exact:"Case"')
        filter_kwargs = [c.kwargs for c in qs.filter.call_args_list]
        self.assertIn({"court_exact": "BGH"}, filter_kwargs)
        self.assertIn({"decision_type_exact": "Urteil"}, filter_kwargs)


class SearchQueryBuilderTest(TestCase):
    """Tests for the shared SearchQueryBuilder."""

    def test_filter_models(self):
        with patch("oldp.apps.search.api.SearchQuerySet") as mock_cls:
            mock_sqs = MagicMock()
            mock_cls.return_value = mock_sqs
            mock_sqs.models.return_value = mock_sqs

            from oldp.apps.cases.models import Case

            builder = SearchQueryBuilder()
            builder.filter_models([Case])
            mock_sqs.models.assert_called_once_with(Case)

    def test_filter_review_status(self):
        with patch("oldp.apps.search.api.SearchQuerySet") as mock_cls:
            mock_sqs = MagicMock()
            mock_cls.return_value = mock_sqs
            mock_sqs.narrow.return_value = mock_sqs

            builder = SearchQueryBuilder()
            builder.filter_review_status("accepted")
            # Applied as a filter-context narrow (not a scoring .filter) so it
            # stays out of the main query string — see filter_review_status.
            mock_sqs.narrow.assert_called_once_with('review_status:"accepted"')

    @override_settings(SEARCH_MAX_SNIPPETS=5, SEARCH_SNIPPET_SIZE=150)
    def test_apply_highlight(self):
        with patch("oldp.apps.search.api.SearchQuerySet") as mock_cls:
            mock_sqs = MagicMock()
            mock_cls.return_value = mock_sqs
            mock_sqs.highlight.return_value = mock_sqs

            builder = SearchQueryBuilder()
            builder.apply_highlight()
            mock_sqs.highlight.assert_called_once_with(
                number_of_fragments=5, fragment_size=150
            )

    def test_apply_date_range_valid(self):
        with patch("oldp.apps.search.api.SearchQuerySet") as mock_cls:
            mock_sqs = MagicMock()
            mock_cls.return_value = mock_sqs
            mock_sqs.filter.return_value = mock_sqs

            builder = SearchQueryBuilder()
            builder.apply_date_range("2020-01-01", "2024-12-31")
            self.assertEqual(mock_sqs.filter.call_count, 2)

    def test_apply_date_range_empty(self):
        with patch("oldp.apps.search.api.SearchQuerySet") as mock_cls:
            mock_sqs = MagicMock()
            mock_cls.return_value = mock_sqs

            builder = SearchQueryBuilder()
            builder.apply_date_range("", "")
            mock_sqs.filter.assert_not_called()

    def test_apply_date_range_invalid_logs_error(self):
        with patch("oldp.apps.search.api.SearchQuerySet") as mock_cls:
            mock_sqs = MagicMock()
            mock_cls.return_value = mock_sqs

            builder = SearchQueryBuilder()
            with self.assertLogs("oldp.apps.search.api", level="ERROR") as cm:
                builder.apply_date_range("not-a-date", "")
            self.assertTrue(any("Invalid start_date" in msg for msg in cm.output))

    def test_fluent_interface(self):
        with patch("oldp.apps.search.api.SearchQuerySet") as mock_cls:
            mock_sqs = MagicMock()
            mock_cls.return_value = mock_sqs
            mock_sqs.models.return_value = mock_sqs
            mock_sqs.filter.return_value = mock_sqs
            mock_sqs.narrow.return_value = mock_sqs
            mock_sqs.highlight.return_value = mock_sqs

            from oldp.apps.cases.models import Case

            result = (
                SearchQueryBuilder()
                .filter_models([Case])
                .filter_review_status()
                .apply_highlight()
                .build()
            )
            self.assertEqual(result, mock_sqs)


class StripHighlightTagsTest(TestCase):
    """Tests for _strip_highlight_tags helper."""

    def test_strips_em_tags(self):
        self.assertEqual(_strip_highlight_tags("foo <em>bar</em> baz"), "foo bar baz")

    def test_no_tags(self):
        self.assertEqual(_strip_highlight_tags("plain text"), "plain text")

    def test_nested_em(self):
        self.assertEqual(_strip_highlight_tags("<em>a</em> and <em>b</em>"), "a and b")


class BuildSnippetsTest(TestCase):
    """Tests for _build_snippets helper."""

    def _make_result(self, text="", highlighted=None):
        result = MagicMock()
        result.text = text
        if highlighted is not None:
            result.highlighted = highlighted
        else:
            del result.highlighted
        return result

    def test_uses_highlighted_fragments(self):
        result = self._make_result(
            text="The quick brown fox jumps",
            highlighted=["quick <em>brown</em> fox"],
        )
        snippets = _build_snippets(result)
        self.assertEqual(len(snippets), 1)
        self.assertEqual(snippets[0]["text"], "quick <em>brown</em> fox")

    def test_snippet_has_required_keys(self):
        result = self._make_result(
            text="some text here",
            highlighted=["some <em>text</em>"],
        )
        snippets = _build_snippets(result)
        self.assertIn("text", snippets[0])
        self.assertIn("offset", snippets[0])
        self.assertIn("length", snippets[0])

    def test_offset_is_correct(self):
        full = "aaa bbb ccc ddd eee"
        result = self._make_result(text=full, highlighted=["ccc <em>ddd</em> eee"])
        snippets = _build_snippets(result)
        self.assertEqual(snippets[0]["offset"], full.find("ccc ddd eee"))

    def test_length_excludes_tags(self):
        result = self._make_result(
            text="hello world",
            highlighted=["<em>hello</em> world"],
        )
        snippets = _build_snippets(result)
        self.assertEqual(snippets[0]["length"], len("hello world"))

    def test_multiple_snippets(self):
        result = self._make_result(
            text="aaa bbb ccc",
            highlighted=["<em>aaa</em>", "<em>bbb</em>", "<em>ccc</em>"],
        )
        snippets = _build_snippets(result)
        self.assertEqual(len(snippets), 3)

    def test_fallback_truncated_text(self):
        long_text = "x" * 500
        result = self._make_result(text=long_text)
        snippets = _build_snippets(result)
        self.assertEqual(len(snippets), 1)
        self.assertTrue(snippets[0]["text"].endswith("..."))
        self.assertEqual(snippets[0]["offset"], 0)

    def test_fallback_short_text(self):
        result = self._make_result(text="short")
        snippets = _build_snippets(result)
        self.assertEqual(snippets[0]["text"], "short")

    def test_offset_negative_one_when_not_found(self):
        result = self._make_result(
            text="original text",
            highlighted=["<em>stemmed</em> variant"],
        )
        snippets = _build_snippets(result)
        self.assertEqual(snippets[0]["offset"], -1)


class SearchResultSerializerSnippetTest(TestCase):
    """Tests for snippet vs full text behavior in SearchResultSerializer."""

    def setUp(self):
        self.factory = APIRequestFactory()

    def _make_result(self, text="Full text content", highlighted=None):
        result = MagicMock()
        result.text = text
        result.title = "Test Title"
        result.pk = "1"
        if highlighted is not None:
            result.highlighted = highlighted
        else:
            del result.highlighted
        return result

    def _make_serializer(self, return_text=False):
        class TestSerializer(SearchResultSerializer):
            class Meta:
                fields = ["title", "text"]

        request = Request(
            self.factory.get(
                "/api/laws/search/",
                {"text": "query", **({"return_text": "1"} if return_text else {})},
            )
        )
        return TestSerializer(context={"request": request})

    def test_default_returns_snippets_not_text(self):
        serializer = self._make_serializer(return_text=False)
        result = self._make_result(text="Full content", highlighted=["<em>Full</em>"])
        data = serializer.to_representation(result)
        self.assertIn("snippets", data)
        self.assertNotIn("text", data)

    def test_return_text_includes_both(self):
        serializer = self._make_serializer(return_text=True)
        result = self._make_result(text="Full content", highlighted=["<em>Full</em>"])
        data = serializer.to_representation(result)
        self.assertIn("snippets", data)
        self.assertIn("text", data)
        self.assertEqual(data["text"], "Full content")

    def test_snippets_is_list_of_dicts(self):
        serializer = self._make_serializer()
        result = self._make_result(text="some text", highlighted=["<em>some</em> text"])
        data = serializer.to_representation(result)
        self.assertIsInstance(data["snippets"], list)
        self.assertIsInstance(data["snippets"][0], dict)

    def test_non_text_fields_preserved(self):
        serializer = self._make_serializer()
        result = self._make_result()
        data = serializer.to_representation(result)
        self.assertIn("title", data)
        self.assertEqual(data["title"], "Test Title")


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

    def test_citing_cases_via_es_returns_error_on_backend_failure(self):
        """Helper must surface a structured error instead of falling
        back to SQL — the law/case detail views render this as a
        notice + deep link to the search page.
        """
        try:
            from elasticsearch.exceptions import ConnectionError as ESConnectionError
        except ImportError:
            self.skipTest("elasticsearch package not installed")

        from oldp.apps.search.utils import citing_cases_via_es

        with patch(
            "haystack.query.SearchQuerySet.count",
            side_effect=ESConnectionError("ES down"),
        ):
            cases, total, error = citing_cases_via_es("cited_laws", "bgb__823")
        self.assertEqual(cases, [])
        self.assertIsNone(total)
        self.assertIsNotNone(error)

    def test_elasticsearch_timeout_raises_timeout_subclass(self):
        """Timeouts must raise the retryable subclass, not the generic one.

        Regression test for the timeout classification added in
        :mod:`oldp.apps.search.utils.is_search_backend_timeout` —
        agents (MCP) and clients (REST) branch on the specific
        exception type to decide whether to retry, so the dispatch
        must distinguish ConnectionTimeout from a flat-out outage.
        """
        try:
            from elasticsearch.exceptions import ConnectionTimeout
        except ImportError:
            self.skipTest("elasticsearch package not installed")

        from oldp.apps.search.exceptions import SearchBackendTimeout

        class FakeParent:
            def list(self, request, *args, **kwargs):
                raise ConnectionTimeout("read timed out")

        class TestView(SearchViewMixin, FakeParent):
            pass

        view = TestView()
        request = Request(self.factory.get("/api/cases/search/", {"text": "test"}))
        with self.assertRaises(SearchBackendTimeout) as ctx:
            view.list(request)
        # ``get_full_details`` produces the structured body that the
        # project-wide ``full_details_exception_handler`` writes back
        # to the response. REST callers see this exact shape.
        body = ctx.exception.get_full_details()
        self.assertEqual(body.get("retryable"), True)
        self.assertIn("hint", body)
        self.assertEqual(body.get("code"), "search_backend_timeout")
        # And SearchBackendTimeout must remain a subclass of the broad
        # SearchBackendUnavailable so existing handlers keep working.
        self.assertIsInstance(ctx.exception, SearchBackendUnavailable)
