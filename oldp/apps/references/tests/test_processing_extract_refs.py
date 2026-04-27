from django.test import TransactionTestCase, tag

from oldp.apps.cases.models import Case
from oldp.apps.cases.processing.processing_steps.extract_refs import (
    ProcessingStep as ExtractRefsStep,
)


@tag("processing")
class ExtractReferencesTestCase(TransactionTestCase):
    """./manage.py dumpdata references --output refs.json"""

    fixtures = [
        "courts/default.json",
        "cases/case_with_references.json",
        "laws/empty_bgb.json",
    ]

    def test_extract_law_refs_from_case(self):
        case = Case.objects.get(pk=1888)

        # law_book_codes left unset — the extractor uses the bundled
        # legal-reference-extraction code list (~1947 codes + unit hints).
        step = ExtractRefsStep(
            law_refs=True,
            case_refs=False,
            assign_refs=True,
        )

        processed = step.process(case)

        # Counts updated for legal-reference-extraction 0.5.0, which adds
        # `Art.` / Grundgesetz citation patterns (CHANGELOG Stream E).
        # The fixture now yields 5 additional Art. GG markers for 3 new
        # target groups (GG/2, GG/14, GG/34) compared to v0.4.x.
        self.assertEqual(33, len(processed.get_references()))

        groups = processed.get_grouped_references()

        self.assertEqual(16, len(groups))
