from unittest.mock import MagicMock, patch

from django.core.cache import cache
from django.http import QueryDict
from django.test import (
    LiveServerTestCase,
    RequestFactory,
    TestCase,
    override_settings,
    tag,
)
from django.urls import reverse

from oldp.apps.search.views import (
    CustomSearchView,
    _get_autocomplete_cache_key,
)
from oldp.utils.test_utils import ElasticsearchTestMixin, es_test


@override_settings(
    STORAGES={
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
        }
    }
)
@tag("views")
class SearchViewsTestCase(ElasticsearchTestMixin, LiveServerTestCase):
    """Test search views with Elasticsearch (uses mock backend by default)."""

    fixtures = [
        "locations/countries.json",
        "locations/states.json",
        "locations/cities.json",
        "courts/courts.json",
        "cases/cases.json",
    ]

    def setUp(self):
        super().setUp()
        # Index fixture data into mock backend
        self.index_fixtures()

    def tearDown(self):
        pass

    def test_facet_url(self):
        view = CustomSearchView()
        # view.get_search_facets()

        assert view

    def get_search_response(self, query_set):
        qs = QueryDict("", mutable=True)
        qs.update(query_set)

        return self.client.get(reverse("haystack_search") + "?" + qs.urlencode())

    @es_test
    def test_search(self):
        res = self.get_search_response(
            {
                "q": "2 aktg",
            }
        )

        self.assertEqual(200, res.status_code)

    @es_test
    def test_search_with_facets(self):
        res = self.get_search_response(
            {
                "q": "2 aktg",
                "selected_facets": "facet_model_name_exact:Case",
            }
        )

        self.assertEqual(200, res.status_code)

    @es_test
    def test_search_from_unassigned_ref(self):
        res = self.get_search_response({"q": "test", "from": "ref"})
        self.assertEqual(200, res.status_code)


def _make_mock_sqs():
    """Create a MagicMock that behaves like an empty SearchQuerySet."""
    mock_sqs = MagicMock()
    mock_sqs.__len__ = MagicMock(return_value=0)
    mock_sqs.__iter__ = MagicMock(return_value=iter([]))
    mock_sqs.__getitem__ = MagicMock(return_value=[])
    mock_sqs.count.return_value = 0
    mock_sqs.facet_counts.return_value = {
        "fields": {},
        "dates": {},
        "queries": {},
    }
    return mock_sqs


@override_settings(
    COMPRESS_ENABLED=False,
    CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "mocked-search-views-cache",
        }
    },
    STORAGES={
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
        }
    },
)
@tag("views")
class MockedSearchViewsTestCase(TestCase):
    """Test search views with mocked search backend (no Elasticsearch required)."""

    def get_search_response(self, query_set):
        qs = QueryDict("", mutable=True)
        qs.update(query_set)
        return self.client.get(reverse("haystack_search") + "?" + qs.urlencode())

    def test_facet_url(self):
        view = CustomSearchView()
        assert view

    @patch(
        "oldp.apps.search.views.CustomSearchForm.search", return_value=_make_mock_sqs()
    )
    def test_search(self, mock_search):
        res = self.get_search_response({"q": "2 aktg"})
        self.assertEqual(200, res.status_code)

    @patch(
        "oldp.apps.search.views.CustomSearchForm.search", return_value=_make_mock_sqs()
    )
    def test_search_with_facets(self, mock_search):
        res = self.get_search_response(
            {
                "q": "2 aktg",
                "selected_facets": "facet_model_name_exact:Case",
            }
        )
        self.assertEqual(200, res.status_code)

    @patch(
        "oldp.apps.search.views.CustomSearchForm.search", return_value=_make_mock_sqs()
    )
    def test_search_from_unassigned_ref(self, mock_search):
        with self.assertLogs("oldp.apps.search.views", level="DEBUG") as cm:
            res = self.get_search_response({"q": "test", "from": "ref"})
        self.assertEqual(200, res.status_code)
        self.assertTrue(any("from=ref" in msg for msg in cm.output))

    @patch(
        "oldp.apps.search.views.CustomSearchForm.search", return_value=_make_mock_sqs()
    )
    def test_search_renders_citation_filter_chip(self, mock_search):
        """``/search/?cited_law_book=bgb&cited_law_section=823`` renders
        the active-filter chip with the ``×`` clear link.

        Regression test for the cited-law filter wiring: the request
        must succeed (status 200), the chip must show the law label
        (falling back to ``(unknown)`` when the law row isn't in the
        test fixtures, which is the case here), and the clear link
        must strip ``cited_law_book`` + ``cited_law_section`` from
        the URL.
        """
        res = self.get_search_response(
            {
                "cited_law_book": "bgb",
                "cited_law_section": "823",
            }
        )
        self.assertEqual(res.status_code, 200)
        body = res.content.decode()
        self.assertIn("active-filters", body)
        # Clear link strips the filter params but keeps any others
        self.assertIn("badge-clear", body)
        self.assertNotIn("cited_law_book=bgb", body.split("badge-clear")[1][:200])

    def test_citation_filter_resolver_resolves_unknown_as_label_none(self):
        """``_resolve_citation_filter`` returns a dict with ``label=None``
        when the slug pair does not exist — the search filter still
        applies (ES returns zero hits, which is correct), but the chip
        falls back to ``(unknown)``.
        """
        from oldp.apps.search.views import _resolve_citation_filter

        out = _resolve_citation_filter(
            {"cited_law_book": "nonexistent", "cited_law_section": "999"}
        )
        self.assertIsNotNone(out)
        self.assertEqual(out["kind"], "law")
        self.assertEqual(out["token"], "nonexistent__999")
        self.assertIsNone(out["label"])

    def test_citation_filter_resolver_returns_none_for_no_params(self):
        from oldp.apps.search.views import _resolve_citation_filter

        self.assertIsNone(_resolve_citation_filter({}))
        self.assertIsNone(_resolve_citation_filter({"q": "anything"}))

    @override_settings(
        CACHES={
            "default": {
                "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
                "LOCATION": "search-test-cache",
            }
        },
        STORAGES={
            "staticfiles": {
                "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
            }
        },
    )
    @patch(
        "oldp.apps.search.views.CustomSearchForm.search", return_value=_make_mock_sqs()
    )
    def test_search_response_is_cached(self, mock_search):
        """Test that search responses are cached by cache_per_role."""
        cache.clear()
        self.get_search_response({"q": "cached query"})
        self.get_search_response({"q": "cached query"})
        mock_search.assert_called_once()  # Second request served from cache
        cache.clear()

    @override_settings(
        CACHES={
            "default": {
                "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
                "LOCATION": "search-facet-test-cache",
            }
        }
    )
    @patch(
        "oldp.apps.search.views.CustomSearchView._build_search_facets", return_value={}
    )
    @patch(
        "oldp.apps.search.views.CustomSearchForm.search", return_value=_make_mock_sqs()
    )
    def test_search_facets_are_cached(self, mock_search, mock_build_facets):
        cache.clear()
        view = CustomSearchView()
        request = RequestFactory().get("/search/?q=test")
        view.request = request
        context = {"facets": {"fields": {}, "dates": {}, "queries": {}}}

        view.get_search_facets(context)
        view.get_search_facets(context)

        mock_build_facets.assert_called_once()
        cache.clear()

    @override_settings(
        CACHES={
            "default": {
                "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
                "LOCATION": "autocomplete-test-cache",
            }
        }
    )
    @patch("oldp.apps.search.views.SearchQuerySet")
    def test_autocomplete_cache_normalizes_query(self, mock_sqs_cls):
        mock_chain = MagicMock()
        mock_chain.__getitem__.return_value = [MagicMock(title="Grundgesetz")]
        mock_sqs = MagicMock()
        mock_sqs.autocomplete.return_value = mock_chain
        mock_sqs_cls.return_value = mock_sqs

        cache.clear()
        res1 = self.client.get("/search/autocomplete?q=%20GG%20")
        res2 = self.client.get("/search/autocomplete?q=gg")

        self.assertEqual(200, res1.status_code)
        self.assertEqual(200, res2.status_code)
        mock_sqs.autocomplete.assert_called_once_with(title="GG")
        mock_sqs_cls.assert_called_once()
        cache.clear()

    @patch("oldp.apps.search.views.SearchQuerySet")
    def test_autocomplete_blank_query_short_circuits(self, mock_sqs_cls):
        res = self.client.get("/search/autocomplete?q=%20%20")

        self.assertEqual(200, res.status_code)
        self.assertJSONEqual(res.content, {"results": []})
        mock_sqs_cls.assert_not_called()

    def test_get_context_data_populates_query_when_haystack_omits_it(self):
        """Regression: Haystack's form_invalid path returns a context without
        "query", which used to crash downstream access with KeyError.
        """
        view = CustomSearchView()
        view.request = RequestFactory().get("/search/?q=hello")
        view.request.LANGUAGE_CODE = "en"

        mock_super_context = {
            "facets": {"fields": {}, "dates": {}, "queries": {}},
            "object_list": [],
        }

        with patch(
            "haystack.generic_views.FacetedSearchMixin.get_context_data",
            return_value=mock_super_context,
        ):
            context = view.get_context_data()

        self.assertEqual("hello", context["query"])
        self.assertIn("search_facets", context)

    def test_get_context_data_defaults_query_to_empty_when_no_q_param(self):
        """When the form_invalid path runs with no q param, query defaults to ""."""
        view = CustomSearchView()
        view.request = RequestFactory().get("/search/")
        view.request.LANGUAGE_CODE = "en"

        mock_super_context = {
            "facets": {"fields": {}, "dates": {}, "queries": {}},
            "object_list": [],
        }

        with patch(
            "haystack.generic_views.FacetedSearchMixin.get_context_data",
            return_value=mock_super_context,
        ):
            context = view.get_context_data()

        self.assertEqual("", context["query"])

    def test_get_context_data_on_backend_error_logs_query(self):
        """Backend errors should return a graceful context and log the query."""
        from elasticsearch.exceptions import TransportError

        view = CustomSearchView()
        view.request = RequestFactory().get("/search/?q=very+long+query")
        view.request.LANGUAGE_CODE = "en"

        backend_error = TransportError(
            400,
            "search_phase_execution_exception",
            {"type": "illegal_argument_exception"},
        )

        with (
            patch(
                "haystack.generic_views.FacetedSearchMixin.get_context_data",
                side_effect=backend_error,
            ),
            self.assertLogs("oldp.apps.search.views", level="ERROR") as cm,
        ):
            context = view.get_context_data()

        self.assertEqual("very long query", context["query"])
        self.assertIn("search_error", context)
        self.assertTrue(
            any("very long query" in msg for msg in cm.output),
            f"Expected query string in log output, got: {cm.output}",
        )

    def test_autocomplete_cache_key_varies_by_host_and_language(self):
        rf = RequestFactory()
        req1 = rf.get("/search/autocomplete?q=gg", HTTP_HOST="example-a.test")
        req1.LANGUAGE_CODE = "en"
        req2 = rf.get("/search/autocomplete?q=GG", HTTP_HOST="example-a.test")
        req2.LANGUAGE_CODE = "en"
        req3 = rf.get("/search/autocomplete?q=gg", HTTP_HOST="example-b.test")
        req3.LANGUAGE_CODE = "en"
        req4 = rf.get("/search/autocomplete?q=gg", HTTP_HOST="example-a.test")
        req4.LANGUAGE_CODE = "de"

        key1 = _get_autocomplete_cache_key(req1, "gg")
        key2 = _get_autocomplete_cache_key(req2, "GG")
        key3 = _get_autocomplete_cache_key(req3, "gg")
        key4 = _get_autocomplete_cache_key(req4, "gg")

        self.assertEqual(key1, key2)  # normalization is case-insensitive for cache key
        self.assertNotEqual(key1, key3)
        self.assertNotEqual(key1, key4)
