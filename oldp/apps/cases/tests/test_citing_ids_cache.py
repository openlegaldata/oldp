"""Tests for the cached citing-case id resolution (internal-tools#5).

``?has_reference_to_law=<id>`` resolved its case ids with a join that walked
~55k rows for a popular section, clocking avg 3.4s / max 10.0s (the upstream
gateway timeout) in the prod slow log. The ids are now cached.

The critical property under test is that caching cannot leak visibility: the
cached list is *structural* (it filters only on ``reference.law_id``), and
review-status filtering happens afterwards on the caller's queryset.
"""

from datetime import date

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext

from oldp.apps.cases.filters import _citing_case_ids_for_law
from oldp.apps.cases.models import Case
from oldp.apps.courts.models import Court
from oldp.apps.laws.models import Law, LawBook
from oldp.apps.references.models import (
    CaseReferenceMarker,
    Reference,
    ReferenceFromCase,
)

User = get_user_model()

LOCMEM = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "citing-ids-tests",
    }
}


@override_settings(CACHES=LOCMEM)
class CitingCaseIdsCacheTestCase(TestCase):
    fixtures = [
        "locations/countries.json",
        "locations/states.json",
        "locations/cities.json",
        "courts/courts.json",
    ]

    @classmethod
    def setUpTestData(cls):
        court = Court.objects.exclude(pk=Court.DEFAULT_ID).first()
        book = LawBook.objects.create(
            code="BGB",
            title="BGB",
            slug="bgb",
            latest=True,
            revision_date="2024-01-01",
            review_status="accepted",
        )
        cls.law = Law.objects.create(
            book=book, section="§ 823", slug="823", review_status="accepted"
        )
        cls.other_law = Law.objects.create(
            book=book, section="§ 249", slug="249", review_status="accepted"
        )

        # Two cases cite the law: one accepted, one still pending.
        cls.accepted = cls._citing_case(court, cls.law, "ZQACC", "accepted")
        cls.pending = cls._citing_case(court, cls.law, "ZQPEND", "pending")
        # A case citing nothing, to prove the filter actually constrains.
        cls.unrelated = Case.objects.create(
            court=court,
            file_number="ZQUNREL",
            slug="zqunrel",
            date=date(2024, 1, 3),
            ecli="ECLI:DE:TEST:ZQUNREL",
            review_status="accepted",
        )

    @classmethod
    def _citing_case(cls, court, law, tag, review_status):
        case = Case.objects.create(
            court=court,
            file_number=tag,
            slug=tag.lower(),
            date=date(2024, 1, 1),
            ecli=f"ECLI:DE:TEST:{tag}",
            review_status=review_status,
        )
        marker = CaseReferenceMarker.objects.create(
            referenced_by=case, text="§ 823 BGB", start=0, end=9
        )
        ref = Reference.objects.create(law=law, to="§ 823 BGB")
        ref.set_to_hash()
        ref.save()
        ReferenceFromCase.objects.create(marker=marker, reference=ref)
        return case

    def setUp(self):
        cache.clear()

    def test_resolves_citing_case_ids(self):
        ids = _citing_case_ids_for_law(self.law.id)

        self.assertEqual(set(ids), {self.accepted.id, self.pending.id})

    def test_second_call_issues_no_sql(self):
        _citing_case_ids_for_law(self.law.id)

        with CaptureQueriesContext(connection) as ctx:
            again = _citing_case_ids_for_law(self.law.id)

        self.assertEqual(set(again), {self.accepted.id, self.pending.id})
        self.assertEqual(
            ctx.captured_queries, [], msg="ids should have been served from cache"
        )

    def test_distinct_laws_cache_independently(self):
        self.assertEqual(
            set(_citing_case_ids_for_law(self.law.id)),
            {self.accepted.id, self.pending.id},
        )
        self.assertEqual(_citing_case_ids_for_law(self.other_law.id), [])

    def test_law_with_no_citers_returns_empty(self):
        self.assertEqual(_citing_case_ids_for_law(self.other_law.id), [])

    def test_cache_does_not_leak_pending_cases_to_anonymous(self):
        """The shared id cache must not bypass per-user visibility.

        The cached list intentionally contains the pending case. Whether a
        requester may *see* it is decided afterwards, by the queryset the
        filter is applied to — so priming the cache as one user must not
        change what another user gets.
        """
        # Prime the cache (contains both accepted and pending ids).
        primed = _citing_case_ids_for_law(self.law.id)
        self.assertIn(self.pending.id, primed)

        url = f"/case/?has_reference_to_law={self.law.id}"

        anon = self.client.get(url)
        self.assertEqual(anon.status_code, 200)
        self.assertContains(anon, "zqacc")
        self.assertNotContains(anon, "zqpend")

        staff = User.objects.create_user(username="s", password="x", is_staff=True)
        self.client.force_login(staff)
        as_staff = self.client.get(url)
        self.assertEqual(as_staff.status_code, 200)
        self.assertContains(as_staff, "zqpend")

    def test_filter_excludes_non_citing_cases(self):
        res = self.client.get(f"/case/?has_reference_to_law={self.law.id}")

        self.assertEqual(res.status_code, 200)
        self.assertNotContains(res, "zqunrel")
