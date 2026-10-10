"""review_date / review_note on cases and the bulk-review guards.

A case rejected by hand in the admin (e.g. after a privacy report) carries a
``review_note`` and must never be re-published by a bulk review step, a bulk
command or the API.
"""

import io
from datetime import date

from django.core.management import call_command
from django.test import TestCase, override_settings, tag

from oldp.apps.cases.exceptions import DuplicateCaseError
from oldp.apps.cases.models import Case
from oldp.apps.cases.processing.processing_steps.set_review_accepted import (
    ProcessingStep as SetReviewAcceptedStep,
)
from oldp.apps.cases.processing.processing_steps.set_review_pending import (
    ProcessingStep as SetReviewPendingStep,
)
from oldp.apps.cases.processing.processing_steps.set_review_rejected import (
    ProcessingStep as SetReviewRejectedStep,
)
from oldp.apps.cases.serializers import CaseUpdateSerializer
from oldp.apps.cases.services.case_creator import CaseCreator
from oldp.apps.courts.models import Court
from oldp.apps.courts.processing.processing_steps.set_review_accepted import (
    ProcessingStep as CourtAcceptStep,
)
from oldp.apps.courts.processing.processing_steps.set_review_pending import (
    ProcessingStep as CourtPendingStep,
)
from oldp.apps.laws.models import Law, LawBook
from oldp.apps.laws.processing.processing_steps.set_lawbook_review_accepted import (
    ProcessingStep as LawBookAcceptStep,
)
from oldp.apps.laws.processing.processing_steps.set_lawbook_review_pending import (
    ProcessingStep as LawBookPendingStep,
)
from oldp.apps.laws.processing.processing_steps.set_review_accepted import (
    ProcessingStep as LawAcceptStep,
)
from oldp.apps.laws.processing.processing_steps.set_review_pending import (
    ProcessingStep as LawPendingStep,
)

FIXTURES = [
    "locations/countries.json",
    "locations/states.json",
    "locations/cities.json",
    "courts/courts.json",
]


@tag("cases", "review")
@override_settings(
    CACHES={"default": {"BACKEND": "django.core.cache.backends.dummy.DummyCache"}}
)
class ReviewDateTestCase(TestCase):
    fixtures = FIXTURES

    def setUp(self):
        self.court = Court.objects.exclude(pk=Court.DEFAULT_ID).first()
        self.case = Case.objects.create(
            court=self.court,
            file_number="REV-001",
            date=date(2022, 5, 4),
            content="<p>x</p>",
            review_status="pending",
        )

    def test_review_date_set_on_create(self):
        self.assertIsNotNone(self.case.review_date)

    def test_review_date_updates_on_status_change_only(self):
        case = Case.objects.get(pk=self.case.pk)
        first = case.review_date
        case.title = "unrelated edit"
        case.save()
        case = Case.objects.get(pk=case.pk)
        self.assertEqual(case.review_date, first)

        case.review_status = "accepted"
        case.save()
        case = Case.objects.get(pk=case.pk)
        self.assertGreater(case.review_date, first)

        second = case.review_date
        case.review_note = "looked fine"
        case.save()
        case = Case.objects.get(pk=case.pk)
        self.assertGreater(case.review_date, second)


@tag("cases", "review")
@override_settings(
    CACHES={"default": {"BACKEND": "django.core.cache.backends.dummy.DummyCache"}}
)
class ManualRejectionTestCase(TestCase):
    """A case rejected by hand with a note stays hidden and cannot come back."""

    fixtures = FIXTURES

    def setUp(self):
        self.court = Court.objects.exclude(pk=Court.DEFAULT_ID).first()
        self.case = Case.objects.create(
            court=self.court,
            file_number="MOD-001",
            date=date(2022, 5, 4),
            content="<p>Der Kläger Max Mustermann, wohnhaft in ...</p>",
            review_status="accepted",
        )
        # What an admin does in the change form after a privacy report.
        self.case.review_status = "rejected"
        self.case.review_note = "Report #1: party identifiable"
        self.case.save()
        self.case.refresh_from_db()

    def test_rejected_case_is_hidden_and_keeps_dedupe_key(self):
        self.assertFalse(Case.get_queryset().filter(pk=self.case.pk).exists())
        self.assertIsNotNone(self.case.review_date)
        creator = CaseCreator(extract_refs=False)
        with self.assertRaises(DuplicateCaseError):
            creator.create_case(
                court_name=self.court.name,
                file_number="MOD-001",
                date=date(2022, 5, 4),
                content="<p>Der Kläger Max Mustermann ...</p>",
            )

    def test_api_patch_cannot_reaccept_rejected_case_with_note(self):
        serializer = CaseUpdateSerializer(
            instance=self.case, data={"review_status": "accepted"}, partial=True
        )
        self.assertFalse(serializer.is_valid())
        self.assertIn("review_status", serializer.errors)

    def test_api_patch_can_accept_rejected_case_without_note(self):
        self.case.review_note = ""
        self.case.save()
        serializer = CaseUpdateSerializer(
            instance=self.case, data={"review_status": "accepted"}, partial=True
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)


@tag("cases", "review")
@override_settings(
    CACHES={"default": {"BACKEND": "django.core.cache.backends.dummy.DummyCache"}}
)
class BulkReviewGuardTestCase(TestCase):
    """Bulk review steps and commands only ever touch pending items."""

    fixtures = FIXTURES

    def setUp(self):
        self.court = Court.objects.exclude(pk=Court.DEFAULT_ID).first()

    def _case(self, status, number):
        return Case.objects.create(
            court=self.court,
            file_number=number,
            date=date(2022, 1, 1),
            content="<p>x</p>",
            review_status=status,
        )

    def test_case_steps_skip_non_pending(self):
        accepted = self._case("accepted", "A-1")
        rejected = self._case("rejected", "R-1")
        pending = self._case("pending", "P-1")

        SetReviewAcceptedStep().process(rejected)
        SetReviewAcceptedStep().process(pending)
        self.assertEqual(rejected.review_status, "rejected")
        self.assertEqual(pending.review_status, "accepted")

        SetReviewRejectedStep().process(accepted)
        self.assertEqual(accepted.review_status, "accepted")
        SetReviewRejectedStep().process(self._case("pending", "P-2"))

        SetReviewPendingStep().process(rejected)
        self.assertEqual(rejected.review_status, "rejected")
        SetReviewPendingStep().process(accepted)
        self.assertEqual(accepted.review_status, "pending")

    def test_bulk_approve_command_skips_rejected_and_accepted(self):
        rejected = self._case("rejected", "R-2")
        rejected.review_note = "rejected by hand"
        rejected.save()
        pending = self._case("pending", "P-3")
        accepted = self._case("accepted", "A-2")
        accepted_date = Case.objects.get(pk=accepted.pk).review_date

        call_command("bulk_approve_cases", stdout=io.StringIO())

        rejected.refresh_from_db()
        pending.refresh_from_db()
        accepted.refresh_from_db()
        self.assertEqual(rejected.review_status, "rejected")
        self.assertEqual(pending.review_status, "accepted")
        self.assertIsNotNone(pending.review_date)
        self.assertEqual(accepted.review_date, accepted_date)

    def test_court_steps_skip_non_pending(self):
        rejected = Court(name="R", review_status="rejected")
        CourtAcceptStep().process(rejected)
        CourtPendingStep().process(rejected)
        self.assertEqual(rejected.review_status, "rejected")
        accepted = Court(name="A", review_status="accepted")
        CourtAcceptStep().process(accepted)
        self.assertEqual(accepted.review_status, "accepted")
        CourtPendingStep().process(accepted)
        self.assertEqual(accepted.review_status, "pending")

    def test_law_steps_skip_non_pending(self):
        book = LawBook.objects.create(
            code="guard", title="Guard", review_status="accepted"
        )
        rejected_law = Law.objects.create(
            book=book,
            section="1",
            slug="guard-1",
            content="x",
            review_status="rejected",
        )
        pending_law = Law.objects.create(
            book=book, section="2", slug="guard-2", content="y", review_status="pending"
        )

        LawAcceptStep().process(rejected_law)
        self.assertEqual(rejected_law.review_status, "rejected")
        LawPendingStep().process(rejected_law)
        self.assertEqual(rejected_law.review_status, "rejected")

        # Accepted book: the accept step must not touch it or cascade.
        LawBookAcceptStep().process(book)
        pending_law.refresh_from_db()
        rejected_law.refresh_from_db()
        self.assertEqual(pending_law.review_status, "pending")
        self.assertEqual(rejected_law.review_status, "rejected")

        # Pending book: cascade promotes pending laws only.
        book.review_status = "pending"
        book.save()
        LawBookAcceptStep().process(book)
        pending_law.refresh_from_db()
        rejected_law.refresh_from_db()
        self.assertEqual(book.review_status, "accepted")
        self.assertEqual(pending_law.review_status, "accepted")
        self.assertEqual(rejected_law.review_status, "rejected")

        # Resetting the book to pending leaves rejected laws alone.
        LawBookPendingStep().process(book)
        pending_law.refresh_from_db()
        rejected_law.refresh_from_db()
        self.assertEqual(pending_law.review_status, "pending")
        self.assertEqual(rejected_law.review_status, "rejected")

        rejected_book = LawBook(code="rb", title="RB", review_status="rejected")
        LawBookPendingStep().process(rejected_book)
        self.assertEqual(rejected_book.review_status, "rejected")
