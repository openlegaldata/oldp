from unittest.mock import MagicMock, patch

from django.http import QueryDict
from django.test import LiveServerTestCase, TestCase, tag
from django.urls import reverse

from oldp.apps.search.views import CustomSearchView
from oldp.utils.test_utils import ElasticsearchTestMixin, es_test


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
