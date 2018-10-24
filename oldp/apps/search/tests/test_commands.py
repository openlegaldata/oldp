from django.core.management import call_command
from django.test import TestCase, tag

from oldp.utils.test_utils import es_test


@tag('commands')
class SearchCommandsTestCase(TestCase):
    fixtures = ['laws/laws.json']

    def setUp(self):
        pass

    def tearDown(self):
        pass

    @es_test
    def test_generate_related_law(self):
        call_command('generate_related', *['law'], **{'limit': 10, 'empty': True})

        # self.assertEqual(Court.objects.all().count(), 10, 'Invalid court count')
