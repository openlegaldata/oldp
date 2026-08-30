"""Unit tests for filter_by_review_status — the shared visibility rule."""

from datetime import date

from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase, override_settings

from oldp.api.mixins import filter_by_review_status
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
class FilterByReviewStatusTestCase(TestCase):
    """Direct tests for the helper function.

    Uses Case as the concrete model since it has both review_status and
    created_by_token (the helper relies on both fields).
    """

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
        cls.user_a = User.objects.create_user(username="alice", password="x")
        cls.user_b = User.objects.create_user(username="bob", password="x")

        read_perm, _ = APITokenPermission.objects.get_or_create(
            resource="cases", action="read"
        )
        group = APITokenPermissionGroup.objects.create(name="cases_read")
        group.permissions.add(read_perm)
        cls.token_a = APIToken.objects.create(
            user=cls.user_a, name="A", permission_group=group
        )

        court = Court.objects.exclude(pk=Court.DEFAULT_ID).first()

        cls.accepted = Case.objects.create(
            court=court,
            file_number="ACC",
            date=date(2026, 1, 1),
            content="<p>a</p>",
            review_status="accepted",
        )
        cls.pending_a = Case.objects.create(
            court=court,
            file_number="PEND-A",
            date=date(2026, 1, 2),
            content="<p>b</p>",
            review_status="pending",
            created_by_token=cls.token_a,
        )
        cls.rejected = Case.objects.create(
            court=court,
            file_number="REJ",
            date=date(2026, 1, 3),
            content="<p>c</p>",
            review_status="rejected",
        )

    def _request(self, user):
        req = self.factory.get("/")
        if user is None:
            from django.contrib.auth.models import AnonymousUser

            req.user = AnonymousUser()
        else:
            req.user = user
        return req

    def _slugs(self, qs):
        return set(qs.values_list("file_number", flat=True))

    def test_no_request_returns_accepted_only(self):
        qs = filter_by_review_status(Case.objects.all(), None)
        self.assertEqual(self._slugs(qs), {"ACC"})

    def test_request_without_user_returns_accepted_only(self):
        req = self.factory.get("/")  # no user attribute
        if hasattr(req, "user"):
            del req.user  # simulate missing user
        qs = filter_by_review_status(Case.objects.all(), req)
        self.assertEqual(self._slugs(qs), {"ACC"})

    def test_anonymous_returns_accepted_only(self):
        qs = filter_by_review_status(Case.objects.all(), self._request(None))
        self.assertEqual(self._slugs(qs), {"ACC"})

    def test_staff_returns_all(self):
        qs = filter_by_review_status(Case.objects.all(), self._request(self.staff))
        self.assertEqual(self._slugs(qs), {"ACC", "PEND-A", "REJ"})

    def test_owner_sees_accepted_plus_own(self):
        qs = filter_by_review_status(Case.objects.all(), self._request(self.user_a))
        self.assertEqual(self._slugs(qs), {"ACC", "PEND-A"})

    def test_other_user_sees_only_accepted(self):
        qs = filter_by_review_status(Case.objects.all(), self._request(self.user_b))
        self.assertEqual(self._slugs(qs), {"ACC"})

    # --- Query shape (internal-tools#5) ---------------------------------

    def test_owner_filter_does_not_join_apitoken(self):
        """The own-content branch must not JOIN accounts_apitoken.

        Traversing ``created_by_token__user`` inside an ``OR`` produced a
        LEFT OUTER JOIN the planner could not trim. It survived into DRF's
        pagination ``COUNT(*)``, which the prod slow log recorded at ~4.3s
        and 585k rows examined per call.
        """
        qs = filter_by_review_status(Case.objects.all(), self._request(self.user_a))

        sql = str(qs.query).lower()
        self.assertNotIn("accounts_apitoken", sql)
        self.assertNotIn("join", sql)

    def test_owner_count_does_not_join_apitoken(self):
        """The same must hold for the COUNT(*) the paginator issues."""
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        qs = filter_by_review_status(Case.objects.all(), self._request(self.user_a))

        with CaptureQueriesContext(connection) as ctx:
            self.assertEqual(qs.count(), 2)

        count_sql = " ".join(
            q["sql"].lower()
            for q in ctx.captured_queries
            if "count(" in q["sql"].lower()
        )
        self.assertTrue(count_sql, "expected a COUNT query to be captured")
        self.assertNotIn("accounts_apitoken", count_sql)

    def test_token_ids_are_resolved_once_per_request(self):
        """Repeated calls on one request must not re-query the token table."""
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        request = self._request(self.user_a)

        with CaptureQueriesContext(connection) as ctx:
            for _ in range(3):
                filter_by_review_status(Case.objects.all(), request)

        token_queries = [
            q for q in ctx.captured_queries if "accounts_apitoken" in q["sql"].lower()
        ]
        self.assertEqual(
            len(token_queries),
            1,
            msg=f"token ids should be memoised on the request, got {len(token_queries)} queries",
        )

    def test_user_without_tokens_sees_accepted_only(self):
        """No tokens must short-circuit rather than emit an empty IN ()."""
        qs = filter_by_review_status(Case.objects.all(), self._request(self.user_b))

        sql = str(qs.query).lower()
        self.assertNotIn("in ()", sql)
        self.assertEqual(self._slugs(qs), {"ACC"})
