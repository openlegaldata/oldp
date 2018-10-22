from django.core.management import call_command
from django.test import TestCase


class LawsCommandsTestCase(TestCase):
    fixtures = [
        'laws/laws.json',
    ]

    def setUp(self):
        pass

    def tearDown(self):
        pass

    def test_process_laws_from_db(self):
        call_command('process_laws',
                     *['assign_topics', 'extract_refs'],
                     **{'limit': 10, 'start': 1, 'input_handler': 'db'})

    # def test_process_cases_save_fs(self):
    #     call_command('process_cases',
    #                  *['assign_topics', 'extract_refs', 'assign_court'],
    #                  **{'limit': 10, 'start': 1, 'input_handler': 'db'})


    # self.assertEqual(Court.objects.all().count(), 10, 'Invalid court count')