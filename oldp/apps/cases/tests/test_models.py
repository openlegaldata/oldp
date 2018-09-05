import logging
import os
from datetime import date
from unittest import skip

from django.core.exceptions import ValidationError
from django.db import DataError
from django.test import TestCase

from oldp.apps.backend.processing import ProcessingError
from oldp.apps.cases.models import Case
from oldp.apps.courts.models import Court
# from oldp.apps.courts.tests.test_models import CourtsTestCase
from oldp.utils.test_utils import mysql_only_test

logger = logging.getLogger(__name__)
RESOURCE_DIR = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'resources')


class CasesModelsTestCase(TestCase):
    fixtures = ['courts.json']

    def setUp(self):
        # CourtsTestCase.set_up_courts()
        pass

    def tearDown(self):
        # CourtsTestCase.tear_down_courts()
        pass

    def test_slug(self):
        Case.objects.create(pk=1, file_number='AB/123', slug='a-case-slug', court_id=Court.DEFAULT_ID)

        self.assertEqual(Case.objects.get(slug='a-case-slug').pk, 1, 'Cannot get case by slug')

    def test_field_validation_2(self):

        try:
            # max_length
            t = 'A' * 201
            c = Case(title=t, file_number=t)
            c.full_clean()
            # c.save()

            raise ValueError('ValidationError should have been raised.')
        except ValidationError:
            pass

    @mysql_only_test
    def test_field_validation(self):

        try:
            # max_length
            t = 'A' * 201
            c = Case(title=t, file_number=t)
            c.save()

            raise ValueError('DataError should have been raised.')
        except DataError:
            pass

    def test_from_hit(self):
        search_hit = {
            'title': 'Case title',
            'slug': 'some-slug',
            'court': Court.DEFAULT_ID,
            'date': '2017-01-01',
            'file_number': 'AB/123',
            'type': 'Urteil',
            'source_url': 'http://openjur.de',
            'pdf_url': 'http://',
            'text': 'Some case text, lorem ipsum.'
        }
        c = Case.from_hit(search_hit)

        self.assertEqual(c.court.get_id(), Court.DEFAULT_ID, 'Invalid court id')
        self.assertEqual(c.file_number, 'AB/123', 'Invalid file number')
        # self.assertEqual(c.get_search_snippet(), '', 'Invalid search snippet')

    def from_json_directory(self, directory):
        """Test from_json_file method with different sources"""

        test_files = os.listdir(os.path.join(RESOURCE_DIR, directory))

        for f in test_files:
            f = os.path.join(RESOURCE_DIR, directory, f)
            self.from_json_file(f)

    def from_json_file(self, f):
        logger.debug('Test resource: %s' % f)

        case = Case.from_json_file(f)
        case.full_clean()
        case.save()

        self.assertGreaterEqual(len(case.text), 300, 'Case text is too short: %s' % case.text)

        logger.debug('Test OK: %s' % case)

    @skip  # TODO fixtures need to fit to test files
    def test_from_json_file_bgh(self):
        self.from_json_directory('from_bgh')

    @skip  # TODO write with django serializer
    def test_section_json(self):
        self.from_json_file(os.path.join(RESOURCE_DIR, 'from_bverfg/bverfg_incorrect_string_value_in_raw.json'))

    @skip  # TODO write with django serializer
    def test_raise_error_from_json_file(self):

        directory = os.path.join(RESOURCE_DIR, 'invalid_cases')
        for f in os.listdir(directory):
            f = os.path.join(directory, f)

            logger.debug('Test resource: %s' % f)

            try:
                Case.from_json_file(f)
                raise ValueError('ProcessingError not raised with %s' % f)
            except ProcessingError:
                pass

    def test_case_serializable(self):
        # TODO >> With post processing FS
        f = os.path.join(RESOURCE_DIR, 'serialized_case.json')

        a = Case(
            file_number='ABC/123',
            date=date(year=2000, month=10, day=2)
        )
        a_json = a.to_json(f)

        b = Case.from_json_file(f)
        b_json = b.to_json()

        self.assertEqual(a_json, b_json)

        # case = Case.from_json_file(f)
        # self.assertEqual(open(f).read(), case.to_json(), 'JSON should be equal')
        # print(case.get_sections())
