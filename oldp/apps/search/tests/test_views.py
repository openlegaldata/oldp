from django.test import TestCase, tag

from oldp.utils.test_utils import es_test


@tag('views')
class SearchViewsTestCase(TestCase):
    """

    Do not forget to put DJANGO_TEST_WITH_ES to true

    """
    fixtures = [
        'search/courts.json',
        'search/cases.json'
    ]

    def setUp(self):
        pass

    def tearDown(self):
        # CourtsTestCase.tear_down_courts()
        pass

    @es_test
    def test_search(self):
        pass

        # self.assertEqual(1, len(res), 'Invalid number of results returned')
        # self.assertEqual('foo-case', res[0].slug, 'Invalid slug returned')

        # print(s.get_results())
