"""``/case/<pk>`` and ``/law/<book>/<pk>`` redirect to the canonical slug URL.

Both routes accept a bare number but used to resolve by slug only, so every
numeric request 404'd. A 30-day nginx sample held 372k such 404s on ``/case/``
alone (ClaudeBot 91k, Googlebot 72k) and a 400-id sample of them resolved to
published cases 400/400 — the ids are answerable, so they are answered.

The property that matters beyond "it redirects" is that the redirect obeys the
same visibility rules as the detail view: an unpublished record must still
404, or the ``Location`` header would leak its slug to anonymous requesters.
"""

from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from oldp.apps.cases.models import Case
from oldp.apps.courts.models import Court
from oldp.apps.laws.models import Law, LawBook

User = get_user_model()

NO_CACHE = {"default": {"BACKEND": "django.core.cache.backends.dummy.DummyCache"}}


@override_settings(CACHES=NO_CACHE)
class CaseNumericIdRedirectTestCase(TestCase):
    fixtures = [
        "locations/countries.json",
        "locations/states.json",
        "locations/cities.json",
        "courts/courts.json",
    ]

    @classmethod
    def setUpTestData(cls):
        court = Court.objects.exclude(pk=Court.DEFAULT_ID).first()
        cls.accepted = Case.objects.create(
            court=court,
            file_number="NUMACC",
            slug="numacc-slug",
            date=date(2026, 1, 1),
            ecli="ECLI:DE:TEST:NUMACC",
            content="<p>a</p>",
            review_status="accepted",
        )
        cls.pending = Case.objects.create(
            court=court,
            file_number="NUMPEND",
            slug="numpend-slug",
            date=date(2026, 1, 2),
            ecli="ECLI:DE:TEST:NUMPEND",
            content="<p>b</p>",
            review_status="pending",
        )

    def test_numeric_id_redirects_permanently_to_slug(self):
        res = self.client.get(f"/case/{self.accepted.pk}")

        self.assertEqual(res.status_code, 301)
        self.assertEqual(res["Location"], "/case/numacc-slug")

    def test_redirect_target_actually_resolves(self):
        """Guards against emitting a 301 to a URL that then 404s."""
        res = self.client.get(f"/case/{self.accepted.pk}", follow=True)

        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.redirect_chain, [("/case/numacc-slug", 301)])

    def test_unknown_id_still_404s(self):
        res = self.client.get("/case/99999999")

        self.assertEqual(res.status_code, 404)

    def test_unpublished_case_404s_for_anonymous(self):
        """The 301 must not leak the slug of a case the requester can't read."""
        res = self.client.get(f"/case/{self.pending.pk}")

        self.assertEqual(res.status_code, 404)
        self.assertNotIn("Location", res)

    def test_unpublished_case_redirects_for_staff(self):
        staff = User.objects.create_user(username="s", password="x", is_staff=True)
        self.client.force_login(staff)

        res = self.client.get(f"/case/{self.pending.pk}")

        self.assertEqual(res.status_code, 301)
        self.assertEqual(res["Location"], "/case/numpend-slug")

    def test_slug_urls_are_unaffected(self):
        """The numeric route is matched first; it must not shadow slugs."""
        res = self.client.get("/case/numacc-slug")

        self.assertEqual(res.status_code, 200)


@override_settings(CACHES=NO_CACHE)
class LawNumericIdRedirectTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.book = LawBook.objects.create(
            code="BGB",
            title="BGB",
            slug="bgb",
            latest=True,
            revision_date="2024-01-01",
            review_status="accepted",
        )
        cls.other_book = LawBook.objects.create(
            code="ZPO",
            title="ZPO",
            slug="zpo",
            latest=True,
            revision_date="2024-01-01",
            review_status="accepted",
        )
        # Slug "823" is numeric *and* a real section — the case that proves
        # the id lookup must not run before the slug lookup.
        cls.section = Law.objects.create(
            book=cls.book, section="§ 823", slug="823", review_status="accepted"
        )
        cls.other_section = Law.objects.create(
            book=cls.other_book, section="§ 91", slug="91", review_status="accepted"
        )

    def test_numeric_slug_still_resolves_as_a_slug(self):
        """`/law/bgb/823` is § 823 BGB, not "law with pk 823"."""
        res = self.client.get("/law/bgb/823")

        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.context["item"].pk, self.section.pk)

    def test_pk_in_wrong_book_redirects_to_canonical_url(self):
        res = self.client.get(f"/law/bgb/{self.other_section.pk}")

        self.assertEqual(res.status_code, 301)
        self.assertEqual(res["Location"], "/law/zpo/91")

    def test_unknown_numeric_404s(self):
        res = self.client.get("/law/bgb/99999999")

        self.assertEqual(res.status_code, 404)

    def test_unknown_non_numeric_slug_404s(self):
        res = self.client.get("/law/bgb/does-not-exist")

        self.assertEqual(res.status_code, 404)
