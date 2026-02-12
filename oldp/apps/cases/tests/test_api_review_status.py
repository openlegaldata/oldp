"""Tests for review_status-based filtering and visibility in the Case API."""

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
from oldp.apps.courts.models import Court

User = get_user_model()


@override_settings(
    CACHES={"default": {"BACKEND": "django.core.cache.backends.dummy.DummyCache"}}
)
class CaseReviewStatusAPITestCase(APITestCase):
    """Tests for review_status filtering and field visibility on the Case API."""

    fixtures = [
        "locations/countries.json",
        "locations/states.json",
        "locations/cities.json",
        "courts/courts.json",
    ]

    def setUp(self):
        self.court = Court.objects.exclude(pk=Court.DEFAULT_ID).first()

        # User A: regular user with token
        self.user_a = User.objects.create_user(
            username="user_a", email="a@example.com", password="pass"
        )
        read_perm, _ = APITokenPermission.objects.get_or_create(
            resource="cases", action="read"
        )
        group = APITokenPermissionGroup.objects.create(name="cases_read")
        group.permissions.add(read_perm)
        self.token_a = APIToken.objects.create(
            user=self.user_a, name="Token A", permission_group=group
        )

        # User B: another regular user with token
        self.user_b = User.objects.create_user(
            username="user_b", email="b@example.com", password="pass"
        )
        self.token_b = APIToken.objects.create(
            user=self.user_b, name="Token B", permission_group=group
        )

        # Staff user
        self.staff_user = User.objects.create_user(
            username="staff", email="staff@example.com", password="pass", is_staff=True
        )
        self.token_staff = APIToken.objects.create(
            user=self.staff_user, name="Token Staff", permission_group=group
        )

        # Cases with different review_status and ownership
        self.accepted_case = Case.objects.create(
            court=self.court,
            file_number="ACC-001",
            date=date(2021, 1, 1),
            content="<p>Accepted case</p>",
            review_status="accepted",
        )
        self.pending_case_a = Case.objects.create(
            court=self.court,
            file_number="PEND-A-001",
            date=date(2021, 2, 1),
            content="<p>Pending case by A</p>",
            review_status="pending",
            created_by_token=self.token_a,
        )
        self.pending_case_b = Case.objects.create(
            court=self.court,
            file_number="PEND-B-001",
            date=date(2021, 3, 1),
            content="<p>Pending case by B</p>",
            review_status="pending",
            created_by_token=self.token_b,
        )
        self.rejected_case = Case.objects.create(
            court=self.court,
            file_number="REJ-001",
            date=date(2021, 4, 1),
            content="<p>Rejected case</p>",
            review_status="rejected",
            created_by_token=self.token_a,
        )

        self.client = APIClient()

    def _get_case_ids(self, response):
        """Extract case IDs from a list response."""
        return {item["id"] for item in response.data["results"]}

    # ── List filtering ─────────────────────────────────────────────

    def test_list_returns_only_accepted_for_token_user(self):
        """Regular user sees only accepted cases and their own non-accepted cases."""
        self.client.force_authenticate(user=self.user_a, token=self.token_a)
        response = self.client.get("/api/cases/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = self._get_case_ids(response)
        # user_a sees: accepted + own pending + own rejected
        self.assertIn(self.accepted_case.pk, ids)
        self.assertIn(self.pending_case_a.pk, ids)
        self.assertIn(self.rejected_case.pk, ids)
        # user_a does NOT see user_b's pending case
        self.assertNotIn(self.pending_case_b.pk, ids)

    def test_list_returns_own_pending_cases(self):
        """User B sees accepted + own pending, not user A's pending/rejected."""
        self.client.force_authenticate(user=self.user_b, token=self.token_b)
        response = self.client.get("/api/cases/")

        ids = self._get_case_ids(response)
        self.assertIn(self.accepted_case.pk, ids)
        self.assertIn(self.pending_case_b.pk, ids)
        self.assertNotIn(self.pending_case_a.pk, ids)
        self.assertNotIn(self.rejected_case.pk, ids)

    def test_list_staff_sees_all(self):
        """Staff user sees all cases regardless of review_status."""
        self.client.force_authenticate(user=self.staff_user, token=self.token_staff)
        response = self.client.get("/api/cases/")

        ids = self._get_case_ids(response)
        self.assertIn(self.accepted_case.pk, ids)
        self.assertIn(self.pending_case_a.pk, ids)
        self.assertIn(self.pending_case_b.pk, ids)
        self.assertIn(self.rejected_case.pk, ids)

    # ── Detail filtering ───────────────────────────────────────────

    def test_detail_returns_404_for_others_pending(self):
        """Non-owner cannot access another user's pending case by ID."""
        self.client.force_authenticate(user=self.user_b, token=self.token_b)
        response = self.client.get(f"/api/cases/{self.pending_case_a.pk}/")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_detail_owner_can_access_pending(self):
        """Owner can access their own pending case."""
        self.client.force_authenticate(user=self.user_a, token=self.token_a)
        response = self.client.get(f"/api/cases/{self.pending_case_a.pk}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_detail_staff_can_access_pending(self):
        """Staff can access any pending case."""
        self.client.force_authenticate(user=self.staff_user, token=self.token_staff)
        response = self.client.get(f"/api/cases/{self.pending_case_a.pk}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    # ── review_status field visibility ─────────────────────────────

    def test_review_status_hidden_for_non_owner(self):
        """Accepted case response has no review_status field for non-owner."""
        self.client.force_authenticate(user=self.user_b, token=self.token_b)
        response = self.client.get(f"/api/cases/{self.accepted_case.pk}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertNotIn("review_status", response.data)

    def test_review_status_visible_for_owner(self):
        """Owner's case response includes review_status."""
        self.client.force_authenticate(user=self.user_a, token=self.token_a)
        response = self.client.get(f"/api/cases/{self.pending_case_a.pk}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("review_status", response.data)
        self.assertEqual(response.data["review_status"], "pending")

    def test_review_status_visible_for_staff(self):
        """Staff user's response includes review_status."""
        self.client.force_authenticate(user=self.staff_user, token=self.token_staff)
        response = self.client.get(f"/api/cases/{self.accepted_case.pk}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("review_status", response.data)
