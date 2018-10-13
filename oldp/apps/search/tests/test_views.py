from django.test import TestCase

from oldp.apps.cases.models import Case
from oldp.apps.search.views import Searcher
from oldp.utils.elasticsearch import delete_elasticsearch_documents
from oldp.utils.test_utils import es_test


class SearchViewsTestCase(TestCase):
    """

    Do not forget to put DJANGO_TEST_WITH_ES to true

    """
    fixtures = [
        'search/courts.json',
        'search/cases.json'
    ]

    def setUp(self):
        delete_elasticsearch_documents(Case)

        for obj in Case.objects.all():
            obj.index()

    def tearDown(self):
        # CourtsTestCase.tear_down_courts()
        pass

    @es_test
    def test_search(self):
        s = Searcher(query='foo')
        s.search()
        res = s.get_results()

        self.assertEqual(1, len(res), 'Invalid number of results returned')
        self.assertEqual('foo-case', res[0].slug, 'Invalid slug returned')

        # print(s.get_results())
