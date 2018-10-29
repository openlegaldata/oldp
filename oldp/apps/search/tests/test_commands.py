from django.core.management import call_command
from django.test import TestCase, tag

from oldp.utils.test_utils import es_test


@tag('commands')
class SearchCommandsTestCase(TestCase):
    fixtures = [
        'laws/laws.json',
        'locations/countries.json', 'locations/states.json', 'locations/cities.json', 'courts/courts.json',
        'cases/cases.json'
    ]

    def setUp(self):
        pass

    def tearDown(self):
        pass

    @es_test
    def test_generate_related_law(self):
        call_command('generate_related', *['law'], **{'limit': 10})

    @es_test
    def test_generate_related_case(self):
        call_command('generate_related', *['case'], **{'limit': 10})
