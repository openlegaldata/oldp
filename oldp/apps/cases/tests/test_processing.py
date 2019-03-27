import json
import logging
import os

from django.test import TestCase, tag

from oldp.apps.cases.models import Case
from oldp.apps.cases.processing.processing_steps.assign_court import ProcessingStep as AssignCourt
from oldp.apps.cases.processing.processing_steps.extract_refs import ProcessingStep as ExtractRefs
from oldp.apps.courts.apps import CourtTypes, CourtLocationLevel
from oldp.apps.courts.models import Court
from oldp.utils.test_utils import TestCaseHelper

logger = logging.getLogger(__name__)
RESOURCE_DIR = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'resources')


@tag('processing')
class CasesProcessingTestCase(TestCase, TestCaseHelper):
    fixtures = [
        'locations/countries.json',
        'locations/states.json',
        'locations/cities.json',
        'courts/courts.json',
        'cases/cases.json'
    ]

    def setUp(self):
        super().setUp()

    def test_extract_law_refs_1(self):
        unprocessed = Case.objects.get(pk=1)
        step = ExtractRefs(law_refs=True, case_refs=False, law_book_codes=['AsylG', 'VwGO'])

        case = step.process(unprocessed)

        # TODO Validate test - old value: 33
        markers = case.get_reference_markers()
        self.assertEqual(3, len(markers), 'Invalid number of markers')

        refs = case.get_references()

        self.assertEqual(4, len(refs), 'Invalid number of references')

    def test_assign_court(self):
        class TestCourtTypes(CourtTypes):
            def get_types(self):
                return {
                    'AG': {
                        'name': 'Amtsgericht',
                        'levels': [CourtLocationLevel.CITY]
                    },
                }

        with self.settings(COURT_TYPES=TestCourtTypes()):

            unprocessed = Case.objects.get(pk=1)

            self.assertEqual(Court.DEFAULT_ID, unprocessed.pk, 'Unprocessed case has already assigned court')

            case = AssignCourt().process(unprocessed)

            self.assertEqual(1166, case.court.pk, 'Invalid court id')
            self.assertEqual('EuGH', case.court.code, 'Invalid court code')

            with_city = AssignCourt().process(Case(court_id=Court.DEFAULT_ID, file_number='with-city', court_raw=json.dumps({
                'name': 'Amtsgericht Aalen',
            })))

            self.assertEqual(1173, with_city.court.pk, 'Invalid court id')

            #
            with_chamber = AssignCourt().process(Case(court_id=Court.DEFAULT_ID, file_number='with-chamber', court_raw=json.dumps({
                'name': 'Bundesverfassungsgericht 5. Kammer',
            })))

            self.assertEqual(1167, with_chamber.court.pk, 'Invalid court id')

            not_found = AssignCourt().process(
                Case(court_id=2, file_number='with-chamber', court_raw=json.dumps({
                    'name': 'Some other court',
                })))

            self.assertEqual(Court.DEFAULT_ID, not_found.court_id, 'Invalid court id')

    def test_assign_court_umlauts(self):

        class TestCourtTypes(CourtTypes):
            def get_types(self):
                return {
                    'EuGH': {
                        'name': 'Europäischer Gerichtshof',
                        'levels': []
                    }
                }

        with self.settings(COURT_TYPES=TestCourtTypes()):

            case_with_umlauts = AssignCourt().process(
                Case(court_id=Court.DEFAULT_ID, file_number='with-umlauts', court_raw='{"name": "Europ\u00e4ischer Gerichtshof 9. Senat"}')
            )

            self.assertEqual(1166, case_with_umlauts.court_id)
        # print(case_with_umlauts.court)
