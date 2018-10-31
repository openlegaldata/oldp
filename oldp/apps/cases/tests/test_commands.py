from django.core.management import call_command
from django.test import TestCase, tag


@tag('commands')
class CasesCommandsTestCase(TestCase):
    fixtures = [
        'locations/countries.json', 'locations/states.json', 'locations/cities.json', 'courts/courts.json',
        'cases/cases.json'
    ]

    def setUp(self):
        pass

    def tearDown(self):
        pass

    def test_process_cases_from_db(self):
        call_command('process_cases',
                     *['extract_refs', 'assign_court'],
                     **{'limit': 1, 'start': 0, 'input_handler': 'db'})

    # def test_process_cases_save_fs(self):
    #     call_command('process_cases',
    #                  *['assign_topics', 'extract_refs', 'assign_court'],
    #                  **{'limit': 10, 'start': 1, 'input_handler': 'db'})


    # self.assertEqual(Court.objects.all().count(), 10, 'Invalid court count')
