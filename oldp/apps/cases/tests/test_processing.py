import logging
import os

from django.test import TestCase, tag

from oldp.apps.cases.models import Case
from oldp.apps.cases.processing.processing_steps.extract_refs import ExtractCaseRefs
from oldp.utils.test_utils import TestCaseHelper

# from oldp.apps.backend.tests import TestCaseHelper

logger = logging.getLogger(__name__)
RESOURCE_DIR = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'resources')


@tag('processing')
class CaseProcessingTest(TestCase, TestCaseHelper):
    fixtures = [
        'cases/courts.json',
        'cases/cases.json'
    ]

    def test_extract_law_refs_1(self):
        unprocessed = Case.objects.get(pk=1)
        case = ExtractCaseRefs(law_refs=True, case_refs=False).process(unprocessed)

        # TODO Validate test - old value: 33
        markers = case.get_reference_markers()
        self.assertEqual(3, len(markers), 'Invalid number of markers')

        refs = case.get_references()

        self.assertEqual(4, len(refs), 'Invalid number of references')

    def test_assign_courts(self):
        pass

    def test_assign_topics(self):
        pass
