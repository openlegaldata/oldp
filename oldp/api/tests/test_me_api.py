"""Tests for /me/ API endpoints.

Tests cover:
- List filtering by authenticated token
- Isolation between different users/tokens
- review_status visibility (always shown for owner)
- Authentication required
"""

from datetime import date

from django.contrib.auth import get_user_model
from django.test import override_settings
from rest_framework import status
from rest_framework.test import APIClient, APITestCase

from oldp.apps.accounts.models import (
    APIToken,
    APITokenPermission,
    APITokenPermissionGroup,
)
from oldp.apps.cases.models import Case
from oldp.apps.courts.models import Court, State
from oldp.apps.laws.models import Law, LawBook

User = get_user_model()


@override_settings(
    CACHES={"default": {"BACKEND": "django.core.cache.backends.dummy.DummyCache"}}
)
class MeEndpointsTestCase(APITestCase):
    """Tests for /me/cases/, /me/law_books/, /me/laws/, /me/courts/ endpoints."""

    fixtures = [
        "locations/countries.json",
        "locations/states.json",
        "locations/cities.json",
        "courts/courts.json",
    ]

    def setUp(self):
        self.court = Court.objects.exclude(pk=Court.DEFAULT_ID).first()

        # Permission group with read access
        read_perm, _ = APITokenPermission.objects.get_or_create(
            resource="cases", action="read"
        )
        group = APITokenPermissionGroup.objects.create(name="read_group")
        group.permissions.add(read_perm)

        # User A with token
        self.user_a = User.objects.create_user(
            username="user_a", email="a@example.com", password="pass"
        )
        self.token_a = APIToken.objects.create(
            user=self.user_a, name="Token A", permission_group=group
        )

        # User B with token
        self.user_b = User.objects.create_user(
            username="user_b", email="b@example.com", password="pass"
        )
        self.token_b = APIToken.objects.create(
            user=self.user_b, name="Token B", permission_group=group
        )

        # Cases
        self.case_a = Case.objects.create(
            court=self.court,
            file_number="ME-CASE-A-001",
            date=date(2021, 1, 1),
            content="<p>Case by token A</p>",
            review_status="pending",
            created_by_token=self.token_a,
        )
        self.case_b = Case.objects.create(
            court=self.court,
            file_number="ME-CASE-B-001",
            date=date(2021, 2, 1),
            content="<p>Case by token B</p>",
            review_status="pending",
            created_by_token=self.token_b,
        )
        self.case_no_token = Case.objects.create(
            court=self.court,
            file_number="ME-CASE-NOTOKEN",
            date=date(2021, 3, 1),
            content="<p>Case without token</p>",
            review_status="accepted",
        )

        # Law books
        self.lawbook_a = LawBook.objects.create(
            code="METEST-A",
            slug="metest-a",
            title="Test Book A",
            revision_date=date(2021, 1, 1),
            latest=True,
            review_status="pending",
            created_by_token=self.token_a,
        )
        self.lawbook_b = LawBook.objects.create(
            code="METEST-B",
            slug="metest-b",
            title="Test Book B",
            revision_date=date(2021, 1, 1),
            latest=True,
            review_status="pending",
            created_by_token=self.token_b,
        )

        # Laws
        self.law_a = Law.objects.create(
            book=self.lawbook_a,
            title="Test Law A",
            section="1",
            content="<p>Law by A</p>",
            slug="metest-a-1",
            review_status="pending",
            created_by_token=self.token_a,
        )
        self.law_b = Law.objects.create(
            book=self.lawbook_b,
            title="Test Law B",
            section="1",
            content="<p>Law by B</p>",
            slug="metest-b-1",
            review_status="pending",
            created_by_token=self.token_b,
        )

        # Courts created by tokens
        state = State.objects.first()
        self.court_a = Court.objects.create(
            name="Me Test Court A",
            code="METESTA",
            slug="me-test-court-a",
            state=state,
            review_status="pending",
            created_by_token=self.token_a,
        )
        self.court_b = Court.objects.create(
            name="Me Test Court B",
            code="METESTB",
            slug="me-test-court-b",
            state=state,
            review_status="pending",
            created_by_token=self.token_b,
        )

        self.client = APIClient()

    # ── Cases ──────────────────────────────────────────────────────

    def test_me_cases_list_shows_own_items(self):
        """Token A sees only cases created by token A."""
        self.client.force_authenticate(user=self.user_a, token=self.token_a)
        response = self.client.get("/api/me/cases/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = {item["id"] for item in response.data["results"]}
        self.assertIn(self.case_a.pk, ids)
        self.assertNotIn(self.case_b.pk, ids)
        self.assertNotIn(self.case_no_token.pk, ids)

    def test_me_cases_list_excludes_others_items(self):
        """Token B does not see token A's cases."""
        self.client.force_authenticate(user=self.user_b, token=self.token_b)
        response = self.client.get("/api/me/cases/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = {item["id"] for item in response.data["results"]}
        self.assertIn(self.case_b.pk, ids)
        self.assertNotIn(self.case_a.pk, ids)

    def test_me_cases_review_status_visible(self):
        """review_status is always visible for the owner's items."""
        self.client.force_authenticate(user=self.user_a, token=self.token_a)
        response = self.client.get("/api/me/cases/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        for item in response.data["results"]:
            self.assertIn("review_status", item)

    # ── Law Books ──────────────────────────────────────────────────

    def test_me_law_books_list_shows_own_items(self):
        """Token A sees only law books created by token A."""
        self.client.force_authenticate(user=self.user_a, token=self.token_a)
        response = self.client.get("/api/me/law_books/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = {item["id"] for item in response.data["results"]}
        self.assertIn(self.lawbook_a.pk, ids)
        self.assertNotIn(self.lawbook_b.pk, ids)

    def test_me_law_books_list_excludes_others_items(self):
        """Token B does not see token A's law books."""
        self.client.force_authenticate(user=self.user_b, token=self.token_b)
        response = self.client.get("/api/me/law_books/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = {item["id"] for item in response.data["results"]}
        self.assertIn(self.lawbook_b.pk, ids)
        self.assertNotIn(self.lawbook_a.pk, ids)

    def test_me_law_books_review_status_visible(self):
        """review_status is visible for owner's law books."""
        self.client.force_authenticate(user=self.user_a, token=self.token_a)
        response = self.client.get("/api/me/law_books/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        for item in response.data["results"]:
            self.assertIn("review_status", item)

    # ── Laws ───────────────────────────────────────────────────────

    def test_me_laws_list_shows_own_items(self):
        """Token A sees only laws created by token A."""
        self.client.force_authenticate(user=self.user_a, token=self.token_a)
        response = self.client.get("/api/me/laws/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = {item["id"] for item in response.data["results"]}
        self.assertIn(self.law_a.pk, ids)
        self.assertNotIn(self.law_b.pk, ids)

    def test_me_laws_list_excludes_others_items(self):
        """Token B does not see token A's laws."""
        self.client.force_authenticate(user=self.user_b, token=self.token_b)
        response = self.client.get("/api/me/laws/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = {item["id"] for item in response.data["results"]}
        self.assertIn(self.law_b.pk, ids)
        self.assertNotIn(self.law_a.pk, ids)

    def test_me_laws_review_status_visible(self):
        """review_status is visible for owner's laws."""
        self.client.force_authenticate(user=self.user_a, token=self.token_a)
        response = self.client.get("/api/me/laws/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        for item in response.data["results"]:
            self.assertIn("review_status", item)

    # ── Courts ─────────────────────────────────────────────────────

    def test_me_courts_list_shows_own_items(self):
        """Token A sees only courts created by token A."""
        self.client.force_authenticate(user=self.user_a, token=self.token_a)
        response = self.client.get("/api/me/courts/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = {item["id"] for item in response.data["results"]}
        self.assertIn(self.court_a.pk, ids)
        self.assertNotIn(self.court_b.pk, ids)

    def test_me_courts_list_excludes_others_items(self):
        """Token B does not see token A's courts."""
        self.client.force_authenticate(user=self.user_b, token=self.token_b)
        response = self.client.get("/api/me/courts/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = {item["id"] for item in response.data["results"]}
        self.assertIn(self.court_b.pk, ids)
        self.assertNotIn(self.court_a.pk, ids)

    def test_me_courts_review_status_visible(self):
        """review_status is visible for owner's courts."""
        self.client.force_authenticate(user=self.user_a, token=self.token_a)
        response = self.client.get("/api/me/courts/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        for item in response.data["results"]:
            self.assertIn("review_status", item)

    # ── Authentication ─────────────────────────────────────────────

    def test_me_cases_requires_auth(self):
        """Unauthenticated request returns 401."""
        response = self.client.get("/api/me/cases/")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_me_law_books_requires_auth(self):
        """Unauthenticated request returns 401."""
        response = self.client.get("/api/me/law_books/")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_me_laws_requires_auth(self):
        """Unauthenticated request returns 401."""
        response = self.client.get("/api/me/laws/")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_me_courts_requires_auth(self):
        """Unauthenticated request returns 401."""
        response = self.client.get("/api/me/courts/")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
