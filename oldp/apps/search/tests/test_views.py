from django.http import QueryDict
from django.test import TestCase, tag

from oldp.utils.test_utils import es_test


@tag('views')
class SearchViewsTestCase(TestCase):
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
        q = QueryDict('selected_facets=facet_model_name_exact:law&q=der&selected_facets=book_code_exact:1-DM-GoldmünzG', mutable=True)

        facets = []
        url_param = 'facet_model_name_exact:law'

        for f in q.getlist('selected_facets'):
            if f != url_param:
                facets.append(f)

        del q['selected_facets']
        q.setlist('selected_facets', facets)

        print(q.dict())
        print()
        print(q.urlencode())

    @es_test
    def test_search(self):
        pass

        # self.assertEqual(1, len(res), 'Invalid number of results returned')
        # self.assertEqual('foo-case', res[0].slug, 'Invalid slug returned')

        # print(s.get_results())
