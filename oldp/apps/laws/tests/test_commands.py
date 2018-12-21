import os

from django.core.management import call_command
from django.test import tag, TransactionTestCase

from oldp.apps.laws.models import Law
from oldp.utils.test_utils import web_test

RESOURCE_DIR = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'resources')


@tag('commands')
class LawsCommandsTestCase(TransactionTestCase):
    fixtures = [
        'laws/laws.json',
    ]

    def test_process_laws_from_fs(self):
        call_command('process_laws',
                     *[],
                     **{'limit': 10, 'start': 1, 'input_handler': 'fs', 'empty': True,
                        'input': os.path.join(RESOURCE_DIR, 'from_bundesgit')})

        self.assertEqual(96, Law.objects.exclude(book__slug='gg').count(), 'Invalid count')

    def test_process_laws_from_db(self):
        call_command('process_laws',
                     *['extract_refs'],
                     **{'limit': 10, 'start': 1, 'input_handler': 'db'})
        pass

    # def test_process_cases_save_fs(self):
    #     call_command('process_cases',
    #                  *['assign_topics', 'extract_refs', 'assign_court'],
    #                  **{'limit': 10, 'start': 1, 'input_handler': 'db'})


    # self.assertEqual(Court.objects.all().count(), 10, 'Invalid court count')

    @web_test
    def test_import_grundgesetz(self):
        call_command('import_grundgesetz', *[], **{'limit': 2, 'empty': True})

    def test_set_law_book_revision(self):
        call_command('set_law_book_revision', *[], **{})

    def test_set_law_book_order(self):
        call_command('set_law_book_order', *[], **{})
