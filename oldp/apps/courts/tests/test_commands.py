import os

from django.conf import settings
from django.core.management import call_command
from django.db import IntegrityError
from django.test import TestCase, tag

from oldp.apps.courts.models import Court


@tag('commands')
class CourtsCommandsTestCase(TestCase):
    fixtures = [
        'locations/countries.json', 'locations/states.json', 'locations/cities.json',
        'courts/courts.json',
    ]

    def setUp(self):
        pass

    def tearDown(self):
        pass

    def test_import_courts_with_empty(self):
        call_command('import_courts', *[
            os.path.join(settings.APPS_DIR, 'courts', 'data', 'ecli.csv')
        ], **{'limit': 10, 'empty': True})

        self.assertEqual(Court.objects.all().count(), 10, 'Invalid court count')

    def test_import_courts_error(self):
        try:
            call_command('import_courts', *[
                os.path.join(settings.APPS_DIR, 'courts', 'data', 'ecli.csv')
            ], **{'limit': 10})
        except IntegrityError:
            return

        raise ValueError('IntegrityError not raised')
