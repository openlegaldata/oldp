from django.test import tag, TransactionTestCase

from oldp.apps.cases.models import Case
from oldp.apps.cases.processing.processing_steps.extract_refs import ProcessingStep as ExtractRefsStep
from oldp.apps.references.processing.processing_steps.extract_refs import BaseExtractRefs


@tag('processing')
class ExtractReferencesTestCase(TransactionTestCase):
    """
    ./manage.py dumpdata references --output refs.json
    """
    fixtures = [
        'courts/default.json',
        'cases/case_with_references.json',
        'laws/empty_bgb.json',
    ]
    law_book_codes = BaseExtractRefs.get_law_books_from_file()

    def test_extract_law_refs_from_case(self):

        case = Case.objects.get(pk=1888)

        step = ExtractRefsStep(law_refs=True, case_refs=False, assign_refs=True, law_book_codes=self.law_book_codes)

        processed = step.process(case)

        self.assertEqual(29, len(processed.get_references()))

        groups = processed.get_grouped_references()

        self.assertEqual(13, len(groups))
