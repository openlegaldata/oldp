from django.http import QueryDict
from django.test import tag, LiveServerTestCase
from django.urls import reverse

from oldp.apps.search.views import CustomSearchView
from oldp.utils.test_utils import es_test


@tag('views')
class SearchViewsTestCase(LiveServerTestCase):
    """

    Do not forget to put DJANGO_TEST_WITH_ES to true

    """
    fixtures = [
        # 'search/courts.json',
        # 'cases/cases.json'
    ]

    def setUp(self):
        pass

    def tearDown(self):
        # CourtsTestCase.tear_down_courts()
        pass

    def test_facet_url(self):
        view = CustomSearchView()
        # view.get_search_facets()


    def get_search_response(self, query_set):
        qs = QueryDict('', mutable=True)
        qs.update(query_set)

        return self.client.get(reverse('haystack_search') + '?' + qs.urlencode())

    @es_test
    def test_search(self):
        res = self.get_search_response({
            'q': '2 aktg',
        })

        self.assertEqual(200, res.status_code)

    @es_test
    def test_search_with_facets(self):
        res = self.get_search_response({
            'q': '2 aktg',
            'selected_facets': 'facet_model_name_exact:Case',
        })

        self.assertEqual(200, res.status_code)
