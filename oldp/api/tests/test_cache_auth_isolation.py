"""The shared ``cache_page`` slot must never hold a privileged response.

The cached read-API viewsets intentionally omit ``vary_on_cookie`` (see
``test_cache_headers``), and ``vary_on_headers`` lists ``Authorization`` --
which a *session*-authenticated user never sends. Before the fix, a logged-in
staff member browsing ``/api/cases/`` stored their response (pending rows,
``review_status`` exposed) in the entry anonymous requests read from, leaking
unpublished content for the whole ``CACHE_TTL``.

``Vary: Cookie`` on the outgoing response does not help: ``SessionMiddleware``
appends it during the response phase, after ``cache_page`` has already keyed
and stored the entry, so it never reaches the Django-internal slot.

These tests drive the real view stack through the Django test client with a
genuine login, and assert isolation in both directions.
"""

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings

from oldp.apps.cases.models import Case
from oldp.apps.courts.models import Country, Court, State

User = get_user_model()

LOCMEM = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "cache-auth-isolation",
    }
}


@override_settings(CACHES=LOCMEM)
class CachePageAuthIsolationTestCase(TestCase):
    """A session-authenticated response must not reach anonymous callers."""

    def setUp(self):
        cache.clear()
        self.staff = User.objects.create_user(
            "zz_cache_staff", "s@example.com", "pw", is_staff=True
        )
        country, _ = Country.objects.get_or_create(
            code="DE", defaults={"name": "Germany"}
        )
        state, _ = State.objects.get_or_create(
            pk=1, defaults={"name": "Test", "country": country, "slug": "test"}
        )
        self.court = Court.objects.create(
            name="ZQ Cache Court",
            slug="zq-cache-court",
            code="ZQCC",
            state=state,
            review_status="accepted",
        )
        self.accepted = Case.objects.create(
            court=self.court,
            slug="zq-cache-accepted",
            file_number="ZQ-ACC-1",
            review_status="accepted",
            content="<p>accepted</p>",
        )
        self.pending = Case.objects.create(
            court=self.court,
            slug="zq-cache-pending",
            file_number="ZQ-PEND-1",
            review_status="pending",
            content="<p>pending</p>",
        )

    def _ids(self, response):
        return {row["id"] for row in response.json()["results"]}

    def test_staff_response_does_not_leak_to_anonymous(self):
        """Staff warms the cache first; anonymous must still see only accepted."""
        staff_client = self.client_class()
        staff_client.force_login(self.staff)
        staff_res = staff_client.get("/api/cases/?limit=50")
        self.assertEqual(staff_res.status_code, 200)
        self.assertIn(self.pending.id, self._ids(staff_res))  # staff sees pending

        anon_res = self.client.get("/api/cases/?limit=50")
        self.assertEqual(anon_res.status_code, 200)
        anon_ids = self._ids(anon_res)
        self.assertIn(self.accepted.id, anon_ids)
        self.assertNotIn(self.pending.id, anon_ids)
        self.assertEqual(anon_res.json()["count"], 1)

    def test_anonymous_response_does_not_starve_staff(self):
        """The reverse direction: anon warms the slot, staff must still see all."""
        anon_res = self.client.get("/api/cases/?limit=50")
        self.assertNotIn(self.pending.id, self._ids(anon_res))

        staff_client = self.client_class()
        staff_client.force_login(self.staff)
        staff_res = staff_client.get("/api/cases/?limit=50")
        self.assertIn(self.pending.id, self._ids(staff_res))
        self.assertEqual(staff_res.json()["count"], 2)

    def test_review_status_not_exposed_to_anonymous_after_staff_request(self):
        """The serialized ``review_status`` field must not leak either."""
        staff_client = self.client_class()
        staff_client.force_login(self.staff)
        staff_client.get("/api/cases/?limit=50")

        anon_res = self.client.get("/api/cases/?limit=50")
        for row in anon_res.json()["results"]:
            self.assertNotIn("review_status", row)

    def test_anonymous_requests_still_share_one_cache_entry(self):
        """The anonymous fast path must stay unfragmented by cookie value.

        This is the property the original cookie-keying change protected, and
        the fix must not regress it: two anonymous callers with *different*
        csrftoken cookies still hit the same entry.
        """
        first = self.client_class()
        first.cookies["csrftoken"] = "token-aaa"
        first.get("/api/cases/?limit=50")

        second = self.client_class()
        second.cookies["csrftoken"] = "token-bbb"
        with self.assertNumQueries(0):
            res = second.get("/api/cases/?limit=50")
        self.assertEqual(res.status_code, 200)
