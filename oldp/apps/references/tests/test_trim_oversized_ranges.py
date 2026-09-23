"""Repair for markers written before the range-expansion cap existed."""

from datetime import date
from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from oldp.apps.laws.models import Law, LawBook
from oldp.apps.references.models import LawReferenceMarker, Reference


class TrimOversizedRangesTestCase(TestCase):
    def setUp(self):
        self.book = LawBook.objects.create(
            code="ZQT",
            title="ZQ Trim",
            slug="zqt",
            revision_date=date(2024, 1, 1),
            latest=True,
            review_status="accepted",
        )
        self.law = Law.objects.create(
            book=self.book,
            title="§ 1",
            slug="1",
            section="§ 1",
            content="<p>x</p>",
            review_status="accepted",
            order=0,
        )
        self.big = LawReferenceMarker.objects.create(
            referenced_by=self.law, text="§§ 1 bis 200", start=0, end=12
        )
        self.big_refs = [Reference.objects.create(to=f"§ {n}") for n in range(1, 21)]
        self.big.references.add(*self.big_refs)

        self.small = LawReferenceMarker.objects.create(
            referenced_by=self.law, text="§§ 5 bis 7", start=20, end=30
        )
        self.small_refs = [Reference.objects.create(to=f"§ {n}") for n in (5, 6, 7)]
        self.small.references.add(*self.small_refs)

    def _run(self, **kw):
        out = StringIO()
        call_command("trim_oversized_reference_ranges", stdout=out, **kw)
        return out.getvalue()

    def test_dry_run_changes_nothing(self):
        out = self._run(limit=5, dry_run=True)
        self.assertIn("Would repair", out)
        self.assertEqual(self.big.references.count(), 20)
        self.assertEqual(Reference.objects.count(), 23)

    def test_oversized_marker_is_trimmed_to_one(self):
        self._run(limit=5)
        self.assertEqual(self.big.references.count(), 1)

    def test_kept_reference_is_the_range_start(self):
        self._run(limit=5)
        kept = self.big.references.get()
        self.assertEqual(kept.pk, min(r.pk for r in self.big_refs))

    def test_marker_under_the_limit_is_untouched(self):
        self._run(limit=5)
        self.assertEqual(self.small.references.count(), 3)

    def test_orphan_reference_rows_are_deleted(self):
        self._run(limit=5)
        # 20 -> 1 leaves 19 deleted; the 3 small ones survive.
        self.assertEqual(Reference.objects.count(), 4)

    def test_is_idempotent(self):
        self._run(limit=5)
        self._run(limit=5)
        self.assertEqual(self.big.references.count(), 1)

    def test_max_markers_caps_the_run(self):
        out = self._run(limit=2, max_markers=1)
        self.assertIn("Repaired 1 marker", out)
