"""Reference lists must render one marker element, not one per reference.

The hidden ``<div class="ref-marker-id-N">`` elements exist only so the JS can
locate markers. Several references routinely share one marker (an enumeration
like "§§ 3, 3b AsylG"), so emitting one per reference was already redundant --
and unbounded. A law whose citation ranges had expanded into 67,888 rows
rendered 67,904 divs (7.4 MB, 88 seconds, 504 at the gateway).

Resolving the marker also cost up to two queries *per reference*, because
``Reference.get_marker()`` walks two reverse m2m accessors.
"""

from datetime import date

from django.test import TestCase

from oldp.apps.laws.models import Law, LawBook
from oldp.apps.references.models import LawReferenceMarker, Reference
from oldp.apps.references.templatetags.reference_tags import distinct_marker_pks


class MarkerDivFanoutTestCase(TestCase):
    def setUp(self):
        self.book = LawBook.objects.create(
            code="ZQV",
            title="ZQ VwGO",
            slug="zqv",
            revision_date=date(2024, 1, 1),
            latest=True,
            review_status="accepted",
        )
        self.law = Law.objects.create(
            book=self.book,
            title="§ 1 ZQ",
            slug="1",
            section="§ 1",
            content="<p>body</p>",
            review_status="accepted",
            order=0,
        )
        self.marker = LawReferenceMarker.objects.create(
            referenced_by=self.law, text="§§ 1 bis 40", start=0, end=11
        )
        # One marker, many references -- the shape a range expansion produces.
        self.refs = [Reference.objects.create(to=f"§ {n} ZQ") for n in range(1, 41)]
        self.marker.references.add(*self.refs)

    def test_distinct_marker_pks_collapses_group_to_one(self):
        pks = distinct_marker_pks(self.refs, self.law)
        self.assertEqual(pks, [self.marker.pk])

    def test_resolution_costs_a_single_query(self):
        """One query regardless of reference count (was up to 2 per reference)."""
        law = Law.objects.get(pk=self.law.pk)
        with self.assertNumQueries(1):
            distinct_marker_pks(self.refs, law)

    def test_map_is_memoised_across_groups(self):
        law = Law.objects.get(pk=self.law.pk)
        with self.assertNumQueries(1):
            distinct_marker_pks(self.refs[:10], law)
            distinct_marker_pks(self.refs[10:], law)

    def test_two_markers_yield_two_pks(self):
        other = LawReferenceMarker.objects.create(
            referenced_by=self.law, text="§ 99", start=20, end=24
        )
        extra = Reference.objects.create(to="§ 99 ZQ")
        other.references.add(extra)
        pks = distinct_marker_pks(self.refs + [extra], self.law)
        self.assertEqual(set(pks), {self.marker.pk, other.pk})

    def test_rendered_page_emits_one_div_per_marker(self):
        """End-to-end: 40 references behind one marker -> one div."""
        res = self.client.get(f"/law/{self.book.slug}/{self.law.slug}")
        self.assertEqual(res.status_code, 200)
        html = res.content.decode()
        self.assertEqual(html.count(f'ref-marker-id-{self.marker.pk}"'), 1)

    def test_unknown_reference_is_skipped(self):
        orphan = Reference.objects.create(to="§ 0 ZQ")
        pks = distinct_marker_pks([orphan], self.law)
        self.assertEqual(pks, [])
