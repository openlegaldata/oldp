"""Unresolved citations are a coverage gap, not an application error.

``save_citations`` emits one summary per document when more than half of its
citations fail to resolve. That summary was logged at ERROR, so a routine
re-extraction run made production look like it was on fire: one batch put
1,350 entries in the log over 12 hours -- a ~60x rise in the ERROR rate --
which buried the genuine errors a log audit is looking for.

Whole document classes fail this way by nature (EU court decisions cite
instruments the patterns do not cover), so the signal must stay; it just must
not compete with real faults.
"""

import logging
from datetime import date

from django.test import TestCase

from oldp.apps.cases.models import Case
from oldp.apps.courts.models import Country, Court, State
from oldp.apps.laws.models import Law, LawBook

LOGGER = "oldp.apps.references.processing.processing_steps.extract_refs"


class ExtractRefsLogLevelTestCase(TestCase):
    """The per-document failure summary must be WARNING, never ERROR."""

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
        self.court = Court.objects.create(
            name="ZQ Log Court", slug="zq-log", code="ZQLOG", state=state
        )
        self.case = Case.objects.create(
            court=self.court,
            slug="zq-log-case",
            file_number="C-332/15",
            content="<p>cites nothing resolvable</p>",
            review_status="accepted",
        )
        book = LawBook.objects.create(
            code="ZQL",
            title="ZQ",
            slug="zql",
            revision_date=date(2024, 1, 1),
            latest=True,
        )
        Law.objects.create(
            book=book, title="§ 1", slug="1", section="§ 1", content="x", order=0
        )

    def _unresolvable_citations(self, n=4):
        """Citations that cannot resolve, so the failure branch is taken."""
        from refex.citations import LawCitation
        from refex.document import Span

        return [
            LawCitation(
                span=Span(0, 9, "§ 1 ZQNOPE"),
                book="ZQNOPE",
                number=str(i),
                unit="paragraph",
            )
            for i in range(1, n + 1)
        ]

    def test_majority_failure_logs_at_warning_not_error(self):
        from refex.document import make_document

        doc = make_document(self.case.content, fmt="html")
        with self.assertLogs(LOGGER, level="WARNING") as logs:
            self.step.save_citations(doc, self._unresolvable_citations(), self.case)
        self.assertTrue(
            any(r.levelno == logging.WARNING for r in logs.records),
            "expected a WARNING summary",
        )
        self.assertFalse(
            any(r.levelno >= logging.ERROR for r in logs.records),
            "the per-document coverage summary must not be logged at ERROR",
        )

    def test_summary_still_reports_the_counts(self):
        """Downgrading the level must not cost the triage information."""
        from refex.document import make_document

        doc = make_document(self.case.content, fmt="html")
        with self.assertLogs(LOGGER, level="WARNING") as logs:
            self.step.save_citations(doc, self._unresolvable_citations(), self.case)
        joined = "\n".join(logs.output)
        self.assertIn("saved=", joined)
        self.assertIn("errors=", joined)
        self.assertIn("% failed", joined)

    def test_log_volume_does_not_scale_with_citation_count(self):
        """One summary per document, however many citations failed.

        This is the property that matters for backfills: per-cite logging is
        what made a full re-extraction run unusable. The level change must not
        reintroduce it by another route.
        """
        from refex.document import make_document

        doc = make_document(self.case.content, fmt="html")
        counts = {}
        for n in (5, 50):
            with self.assertLogs(LOGGER, level="DEBUG") as logs:
                self.step.save_citations(
                    doc, self._unresolvable_citations(n), self.case
                )
            counts[n] = len([r for r in logs.records if r.levelno >= logging.WARNING])
        self.assertEqual(counts[5], 1)
        self.assertEqual(counts[50], 1, f"log volume scaled with citations: {counts}")
