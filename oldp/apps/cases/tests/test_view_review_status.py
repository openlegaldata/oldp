"""HTML view visibility checks: Case.get_queryset() and the cases views.

Complements oldp/api/tests/test_mixins.py (helper-level) and
test_api_review_status.py (DRF level) — focused on the model static + the
list/detail Django views.
"""

from datetime import date

from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse

from oldp.apps.accounts.models import (
    APIToken,
    APITokenPermission,
    APITokenPermissionGroup,
)
from oldp.apps.cases.models import Case
from oldp.apps.courts.models import Court

User = get_user_model()


@override_settings(
    CACHES={"default": {"BACKEND": "django.core.cache.backends.dummy.DummyCache"}}
)
class CaseGetQuerysetTestCase(TestCase):
    """Direct tests for Case.get_queryset(request) — uses the shared helper."""

    fixtures = [
        "locations/countries.json",
        "locations/states.json",
        "locations/cities.json",
        "courts/courts.json",
    ]

    @classmethod
    def setUpTestData(cls):
        cls.factory = RequestFactory()
        cls.staff = User.objects.create_user(
            username="staff", password="x", is_staff=True
        )
        cls.regular = User.objects.create_user(username="reg", password="x")

        read_perm, _ = APITokenPermission.objects.get_or_create(
            resource="cases", action="read"
        )
        group = APITokenPermissionGroup.objects.create(name="cases_read")
        group.permissions.add(read_perm)
        cls.token_reg = APIToken.objects.create(
            user=cls.regular, name="reg-token", permission_group=group
        )

        court = Court.objects.exclude(pk=Court.DEFAULT_ID).first()
        cls.accepted = Case.objects.create(
            court=court,
            file_number="ACC",
            date=date(2026, 1, 1),
            content="<p>a</p>",
            review_status="accepted",
        )
        cls.pending_own = Case.objects.create(
            court=court,
            file_number="PEND-OWN",
            date=date(2026, 1, 2),
            content="<p>b</p>",
            review_status="pending",
            created_by_token=cls.token_reg,
        )
        cls.pending_other = Case.objects.create(
            court=court,
            file_number="PEND-OTHER",
            date=date(2026, 1, 3),
            content="<p>c</p>",
            review_status="pending",
        )

    def _request(self, user):
        req = self.factory.get("/")
        if user is None:
            from django.contrib.auth.models import AnonymousUser

            req.user = AnonymousUser()
        else:
            req.user = user
        return req

    def _fns(self, qs):
        return set(qs.values_list("file_number", flat=True))

    def test_no_request_returns_accepted_only(self):
        self.assertEqual(self._fns(Case.get_queryset()), {"ACC"})

    def test_anon_returns_accepted_only(self):
        self.assertEqual(self._fns(Case.get_queryset(self._request(None))), {"ACC"})

    def test_staff_returns_all(self):
        self.assertEqual(
            self._fns(Case.get_queryset(self._request(self.staff))),
            {"ACC", "PEND-OWN", "PEND-OTHER"},
        )

    def test_owner_sees_accepted_plus_own(self):
        self.assertEqual(
            self._fns(Case.get_queryset(self._request(self.regular))),
            {"ACC", "PEND-OWN"},
        )


@override_settings(
    CACHES={"default": {"BACKEND": "django.core.cache.backends.dummy.DummyCache"}}
)
class CaseViewVisibilityTestCase(TestCase):
    """List + detail HTML views must respect Case.get_queryset()."""

    fixtures = [
        "locations/countries.json",
        "locations/states.json",
        "locations/cities.json",
        "courts/courts.json",
    ]

    @classmethod
    def setUpTestData(cls):
        cls.staff = User.objects.create_user(
            username="staff", password="pass", is_staff=True
        )

        court = Court.objects.exclude(pk=Court.DEFAULT_ID).first()
        cls.accepted = Case.objects.create(
            court=court,
            file_number="ACC-12345",
            slug="acc-12345",
            date=date(2026, 1, 1),
            content="<p>accepted body</p>",
            review_status="accepted",
        )
        cls.pending = Case.objects.create(
            court=court,
            file_number="PEND-99999",
            slug="pend-99999",
            date=date(2026, 1, 2),
            content="<p>pending body</p>",
            review_status="pending",
        )

    def test_list_anon_hides_pending(self):
        res = self.client.get(reverse("cases:index"))
        self.assertContains(res, "ACC-12345")
        self.assertNotContains(res, "PEND-99999")

    def test_list_staff_shows_pending(self):
        self.client.force_login(self.staff)
        res = self.client.get(reverse("cases:index"))
        self.assertContains(res, "ACC-12345")
        self.assertContains(res, "PEND-99999")

    def test_detail_anon_404s_on_pending(self):
        res = self.client.get(reverse("cases:case", args=("pend-99999",)))
        self.assertEqual(res.status_code, 404)

    def test_detail_staff_renders_pending(self):
        self.client.force_login(self.staff)
        res = self.client.get(reverse("cases:case", args=("pend-99999",)))
        self.assertEqual(res.status_code, 200)


@override_settings(
    CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "case-detail-cache-tests",
        }
    }
)
class CaseDetailCacheReviewStatusTestCase(TestCase):
    """Regression: the case detail view caches under slug-only keys.

    Without per-role scoping, a staff/creator preview would poison the
    cache and serve pending/rejected cases to anonymous visitors.
    """

    fixtures = [
        "locations/countries.json",
        "locations/states.json",
        "locations/cities.json",
        "courts/courts.json",
    ]

    @classmethod
    def setUpTestData(cls):
        cls.staff = User.objects.create_user(
            username="staff", password="pass", is_staff=True
        )
        court = Court.objects.exclude(pk=Court.DEFAULT_ID).first()
        cls.accepted = Case.objects.create(
            court=court,
            file_number="ACC-CACHE",
            slug="acc-cache",
            date=date(2026, 1, 1),
            content="<p>accepted body</p>",
            review_status="accepted",
        )
        cls.pending = Case.objects.create(
            court=court,
            file_number="PEND-CACHE",
            slug="pend-cache",
            date=date(2026, 1, 2),
            content="<p>pending body</p>",
            review_status="pending",
        )

    def setUp(self):
        from django.core.cache import cache

        cache.clear()

    def test_pending_case_not_leaked_to_anon_after_staff_warm(self):
        self.client.force_login(self.staff)
        staff_res = self.client.get(reverse("cases:case", args=("pend-cache",)))
        self.assertEqual(staff_res.status_code, 200)

        self.client.logout()
        anon_res = self.client.get(reverse("cases:case", args=("pend-cache",)))
        self.assertEqual(anon_res.status_code, 404)

    def test_no_cache_entries_written_for_pending(self):
        from django.core.cache import cache

        from oldp.apps.cases.cache import (
            CASE_CONTENT_ANON_KEY,
            CASE_DATA_KEY,
            CASE_PUBLIC_MARKERS_KEY,
        )

        self.client.force_login(self.staff)
        self.client.get(reverse("cases:case", args=("pend-cache",)))

        for tpl in (CASE_DATA_KEY, CASE_PUBLIC_MARKERS_KEY, CASE_CONTENT_ANON_KEY):
            self.assertIsNone(cache.get(tpl % "pend-cache"), tpl)

    def test_accepted_case_invalidated_on_demotion(self):
        warm = self.client.get(reverse("cases:case", args=("acc-cache",)))
        self.assertEqual(warm.status_code, 200)

        self.accepted.review_status = "pending"
        self.accepted.save()

        anon_res = self.client.get(reverse("cases:case", args=("acc-cache",)))
        self.assertEqual(anon_res.status_code, 404)
