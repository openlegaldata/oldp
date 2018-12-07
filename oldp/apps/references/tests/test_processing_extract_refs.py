from django.test import TestCase, tag

from oldp.apps.cases.models import Case
from oldp.apps.cases.processing.processing_steps.extract_refs import ProcessingStep as ExtractRefsStep
from oldp.apps.references.models import Reference


@tag('processing')
class ExtractReferencesTestCase(TestCase):
    """
    ./manage.py dumpdata references --output refs.json
    """
    fixtures = [
        'courts/default.json',
        'cases/case_with_references.json',
        'laws/empty_bgb.json',
    ]

    def test_extract_law_refs(self):
        # call_command('assign_references', *[], **{})
        case = Case.objects.get(pk=1888)

        step = ExtractRefsStep(law_refs=True, case_refs=False, assign_refs=True)

        c = step.process(case)

        extracted_refs = Reference.objects.all()

        # for r in extracted_refs:
        #     print(r)

        self.assertEqual(24, len(extracted_refs))

        c.get_references()

        groups = c.get_grouped_references()

        self.assertEqual(8, len(groups))
