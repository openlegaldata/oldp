import os

from django.conf import settings
from django.core.management import call_command
from django.db import IntegrityError
from django.test import TestCase

from oldp.apps.courts.management.commands.enrich_courts import Command as EnrichCourtsCommand
from oldp.apps.courts.models import Court
from oldp.utils.test_utils import web_test


class CourtsCommandsTestCase(TestCase):
    fixtures = ['courts.json']

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

    @web_test
    def test_enrich_courts_cmd(self):
        opts = {
            'start': 0,
            'limit': 3
        }
        call_command('enrich_courts', *[], **opts)

        res = Court.objects.exclude(image__isnull=True).exclude(image__exact='').exclude(description__exact='')

        self.assertEqual(len(res), 2, 'There should be 2 enriched courts')

        # for r in res:
        #     print(r.__dict__)

    @web_test
    def test_enrich_court(self):

        cmd = EnrichCourtsCommand()
        court = Court.objects.get(slug='bverfg')
        res = cmd.enrich_court(court)

        self.assertEqual(res.image.width, 180, 'Invalid image width')
        self.assertEqual(res.image.height, 249, 'Invalid image height')
        self.assertTrue(res.description.startswith('Das Bundesverfassungsgericht (BVerfG) ist in der Bundesrepublik '
                                                   'Deutschland das Verfassungsgericht des Bundes.'),
                        'Invalid description')
