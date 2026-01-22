from django.http import QueryDict
from django.test import LiveServerTestCase, tag
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
