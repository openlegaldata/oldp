from django.core.management import call_command
from django.test import tag, TestCase

from oldp.apps.courts.apps import CourtLocationLevel, CourtTypes
from oldp.apps.courts.models import Court
from oldp.apps.courts.processing.processing_steps.enrich_from_wikipedia import ProcessingStep as EnrichFromWikipedia
from oldp.apps.courts.processing.processing_steps.set_aliases import ProcessingStep as SetAliases
from oldp.utils.test_utils import web_test


@tag('processing')
class CourtsProcessingTestCase(TestCase):
    fixtures = [
        'locations/countries.json', 'locations/states.json', 'locations/cities.json',
        'courts/courts.json',
    ]

    def setUp(self):
        pass

    def tearDown(self):
        pass


    @web_test
    def test_enrich_courts_cmd(self):
        opts = {
            'start': 0,
            'limit': 3
        }
        call_command('process_courts', *['enrich_from_wikipedia'], **opts)

        res = Court.objects.exclude(image__isnull=True).exclude(image__exact='').exclude(description__exact='')

        self.assertEqual(len(res), 2, 'There should be 2 enriched courts')

        # for r in res:
        #     print(r.__dict__)

    @web_test
    def test_enrich_court(self):
        step = EnrichFromWikipedia()

        court = Court.objects.get(slug='bverfg')
        res = step.process(court)

        self.assertEqual(res.image.width, 180, 'Invalid image width')
        self.assertEqual(res.image.height, 249, 'Invalid image height')
        self.assertTrue(res.description.startswith('Das Bundesverfassungsgericht (BVerfG) ist in der Bundesrepublik '
                                                   'Deutschland das Verfassungsgericht des Bundes.'),
                        'Invalid description')

    # Test depends on German court types
    def test_set_aliases(self):
        class TestCourtTypes(CourtTypes):
            def get_types(self):
                return {
                    'AG': {
                        'name': 'Amtsgericht',
                        'levels': [CourtLocationLevel.CITY]
                    }
                }

        with self.settings(COURT_TYPES=TestCourtTypes()):

            step = SetAliases()

            # Frankfurt am Main
            step.process(Court.objects.get(pk=2001)).save()

            self.assertEqual(2001, Court.objects.get(aliases__contains='AG Frankfurt (Main)').pk)

        # for court in Court.objects.filter(pk__gte=1000):
        #     res = step.process(court)
