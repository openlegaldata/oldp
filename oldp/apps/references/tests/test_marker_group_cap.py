"""One marker must not produce an unbounded number of references.

``_expand_range`` caps a single citation carrying ``range_end`` -- but that is
not the shape real extractor output takes. No engine sets ``range_end``; it is
only copied in the resolver. An over-wide citation arrives as N separate
``LawCitation`` objects sharing one span, which ``_group_by_span`` collapses
onto a single marker, so the per-citation cap never fires on live input.

Production carried a marker holding 16,464 references from a misparsed
"§§ 154 bis 16617". A marker is rendered and fetched as a unit, so an unbounded
group is a page-level failure.
"""

from datetime import date

from django.test import TestCase
from refex.citations import LawCitation
from refex.document import Span, make_document

from oldp.apps.cases.models import Case
from oldp.apps.courts.models import Country, Court, State
from oldp.apps.laws.models import Law, LawBook
from oldp.apps.references.processing.processing_steps.extract_refs import (
    BaseExtractRefs,
)

LIMIT = BaseExtractRefs.RANGE_EXPANSION_LIMIT


class MarkerGroupCapTestCase(TestCase):
    def setUp(self):
        from oldp.apps.cases.processing.processing_steps.extract_refs import (
            ProcessingStep as ExtractRefsStep,
        )

        self.step = ExtractRefsStep(law_refs=True, case_refs=False, assign_refs=True)

        country, _ = Country.objects.get_or_create(
            code="DE", defaults={"name": "Germany"}
        )
        state, _ = State.objects.get_or_create(
            pk=1, defaults={"name": "T", "country": country, "slug": "t"}
        )
        court = Court.objects.create(
            name="ZQ Cap Court", slug="zq-cap", code="ZQCAP", state=state
        )
        self.case = Case.objects.create(
            court=court,
            slug="zq-cap-case",
            file_number="ZQ 1/24",
            content="<p>Nach §§ 154 bis 16617 ZQB gilt.</p>",
            review_status="accepted",
        )
        book = LawBook.objects.create(
            code="ZQB",
            title="ZQ Book",
            slug="zqb",
            revision_date=date(2024, 1, 1),
            latest=True,
            review_status="accepted",
        )
        for n in (154, 16617):
            Law.objects.create(
                book=book,
                title=f"§ {n}",
                slug=str(n),
                section=f"§ {n}",
                content="x",
                review_status="accepted",
                order=n,
            )

    def _wide_group(self, n):
        """N citations sharing one span -- the shape a wide range really takes."""
        span = Span(0, 24, "§§ 154 bis 16617 ZQB")
        return [
            LawCitation(span=span, book="ZQB", number=str(154 + i), unit="paragraph")
            for i in range(n)
        ]

    def test_group_within_the_cap_is_untouched(self):
        group = self._wide_group(LIMIT)
        self.assertEqual(len(self.step._cap_group(group, self.case)), LIMIT)

    def test_group_past_the_cap_keeps_endpoints_only(self):
        group = self._wide_group(LIMIT + 50)
        capped = self.step._cap_group(group, self.case)
        self.assertEqual(len(capped), 2)
        self.assertEqual(capped[0].number, "154")
        self.assertEqual(capped[1].number, str(154 + LIMIT + 49))

    def test_cap_is_logged(self):
        with self.assertLogs(
            "oldp.apps.references.processing.processing_steps.extract_refs",
            level="WARNING",
        ) as logs:
            self.step._cap_group(self._wide_group(LIMIT + 1), self.case)
        self.assertTrue(any("16617" in line for line in logs.output))

    def test_save_citations_writes_at_most_the_cap(self):
        """End-to-end: a 16,464-citation group must not write 16,464 rows."""
        doc = make_document(self.case.content, fmt="html")
        markers, refs = self.step.save_citations(
            doc, self._wide_group(16464), self.case
        )
        self.assertEqual(len(markers), 1)
        self.assertLessEqual(len(refs), 2)
