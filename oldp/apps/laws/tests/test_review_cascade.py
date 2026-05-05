"""Tests for the LawBook review_status processing steps cascading to child laws."""

from datetime import date

from django.test import TestCase

from oldp.apps.laws.models import Law, LawBook
from oldp.apps.laws.processing.processing_steps.set_lawbook_review_accepted import (
    ProcessingStep as AcceptStep,
)
from oldp.apps.laws.processing.processing_steps.set_lawbook_review_pending import (
    ProcessingStep as PendingStep,
)


class LawBookReviewCascadeTestCase(TestCase):
    """When a LawBook's review_status changes, child Law rows must follow."""

    def setUp(self):
        self.book = LawBook.objects.create(
            slug="cascade-book",
            code="CASCADE",
            title="Cascade test book",
            order=1,
            latest=True,
            revision_date=date(2026, 1, 1),
            review_status="pending",
        )
        self.law_pending_a = Law.objects.create(
            book=self.book,
            slug="art-1",
            section="Art 1",
            title="L1",
            order=10,
            review_status="pending",
        )
        self.law_pending_b = Law.objects.create(
            book=self.book,
            slug="art-2",
            section="Art 2",
            title="L2",
            order=20,
            review_status="pending",
        )

    def test_accept_cascades_to_laws(self):
        AcceptStep().process(self.book)
        self.book.save()

        self.law_pending_a.refresh_from_db()
        self.law_pending_b.refresh_from_db()
        self.assertEqual(self.law_pending_a.review_status, "accepted")
        self.assertEqual(self.law_pending_b.review_status, "accepted")

    def test_accept_does_not_touch_other_books(self):
        other_book = LawBook.objects.create(
            slug="other-book",
            code="OTHER",
            title="Other",
            order=2,
            latest=True,
            revision_date=date(2026, 1, 1),
            review_status="pending",
        )
        other_law = Law.objects.create(
            book=other_book,
            slug="x",
            section="X",
            title="X",
            order=10,
            review_status="pending",
        )

        AcceptStep().process(self.book)
        self.book.save()

        other_law.refresh_from_db()
        self.assertEqual(other_law.review_status, "pending")

    def test_pending_cascades_to_laws(self):
        Law.objects.filter(book=self.book).update(review_status="accepted")

        PendingStep().process(self.book)
        self.book.save()

        self.law_pending_a.refresh_from_db()
        self.law_pending_b.refresh_from_db()
        self.assertEqual(self.law_pending_a.review_status, "pending")
        self.assertEqual(self.law_pending_b.review_status, "pending")

    def test_accept_unsaved_book_does_not_query(self):
        """A book without pk (never saved) should be a no-op for the cascade."""
        unsaved = LawBook(
            slug="unsaved",
            code="UNSAVED",
            title="Unsaved",
            order=99,
            revision_date=date(2026, 1, 1),
            review_status="pending",
        )
        # Must not raise.
        AcceptStep().process(unsaved)
        self.assertEqual(unsaved.review_status, "accepted")
