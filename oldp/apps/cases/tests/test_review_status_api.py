"""Tests for case review_status API: filtering and PATCH permissions.

Tests cover:
- Staff user with token can PATCH review_status
- Non-staff user with token gets 403
- Staff user without token (session auth) can PATCH
- Non-staff user without token gets 403
- Unauthenticated user gets 401
- review_status filter works
- created_by_token filter works
"""

from django.contrib.auth.models import User
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


@override_settings(
    CACHES={"default": {"BACKEND": "django.core.cache.backends.dummy.DummyCache"}},
    STORAGES={
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"
        },
    },
)
class CaseReviewStatusAPITestCase(APITestCase):
    """Tests for review_status PATCH and filter on cases API."""

    fixtures = [
        "locations/countries.json",
        "locations/states.json",
        "locations/cities.json",
        "courts/courts.json",
    ]

    def setUp(self):
        # Staff user + token
        self.staff_user = User.objects.create_user(
            username="staffuser",
            email="staff@example.com",
            password="testpass123",
            is_staff=True,
        )
        self.staff_write_perm, _ = APITokenPermission.objects.get_or_create(
            resource="cases", action="write"
        )
        self.staff_read_perm, _ = APITokenPermission.objects.get_or_create(
            resource="cases", action="read"
        )
        self.staff_group = APITokenPermissionGroup.objects.create(name="staff_group")
        self.staff_group.permissions.add(self.staff_write_perm, self.staff_read_perm)
        self.staff_token = APIToken.objects.create(
            user=self.staff_user,
            name="Staff Token",
            permission_group=self.staff_group,
        )

        # Non-staff user + token (ingestor-like)
        self.regular_user = User.objects.create_user(
            username="ingestor",
            email="ingestor@example.com",
            password="testpass123",
            is_staff=False,
        )
        self.regular_group = APITokenPermissionGroup.objects.create(
            name="ingestor_group"
        )
        self.regular_group.permissions.add(self.staff_write_perm, self.staff_read_perm)
        self.regular_token = APIToken.objects.create(
            user=self.regular_user,
            name="Ingestor Token",
            permission_group=self.regular_group,
        )

        # Create a pending case
        self.court = Court.objects.exclude(pk=Court.DEFAULT_ID).first()
        self.pending_case = Case.objects.create(
            court=self.court,
            file_number="REVIEW-001/24",
            date="2024-06-01",
            content="<p>Test case content for review status testing</p>",
            review_status="pending",
            created_by_token=self.regular_token,
        )

        # Create an accepted case
        self.accepted_case = Case.objects.create(
            court=self.court,
            file_number="REVIEW-002/24",
            date="2024-06-02",
            content="<p>Accepted case content</p>",
            review_status="accepted",
        )

        self.client = APIClient()

    # ── PATCH with staff token ──

    def test_staff_token_can_patch_review_status(self):
        """Staff user with token can change review_status via PATCH."""
        self.client.force_authenticate(user=self.staff_user, token=self.staff_token)
        response = self.client.patch(
            f"/api/cases/{self.pending_case.id}/",
            {"review_status": "accepted"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.pending_case.refresh_from_db()
        self.assertEqual(self.pending_case.review_status, "accepted")

    def test_staff_token_can_reject_case(self):
        """Staff user can reject a pending case."""
        self.client.force_authenticate(user=self.staff_user, token=self.staff_token)
        response = self.client.patch(
            f"/api/cases/{self.pending_case.id}/",
            {"review_status": "rejected"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.pending_case.refresh_from_db()
        self.assertEqual(self.pending_case.review_status, "rejected")

    def test_staff_token_invalid_review_status_rejected(self):
        """Invalid review_status value returns 400."""
        self.client.force_authenticate(user=self.staff_user, token=self.staff_token)
        response = self.client.patch(
            f"/api/cases/{self.pending_case.id}/",
            {"review_status": "invalid_value"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    # ── PATCH with non-staff token ──

    def test_non_staff_token_cannot_patch_review_status(self):
        """Non-staff user with token gets 403 on PATCH."""
        self.client.force_authenticate(user=self.regular_user, token=self.regular_token)
        response = self.client.patch(
            f"/api/cases/{self.pending_case.id}/",
            {"review_status": "accepted"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.pending_case.refresh_from_db()
        self.assertEqual(self.pending_case.review_status, "pending")

    # ── PATCH with session auth (no token) ──

    def test_staff_session_can_patch_review_status(self):
        """Staff user via session auth (no token) can PATCH review_status."""
        self.client.force_authenticate(user=self.staff_user)
        response = self.client.patch(
            f"/api/cases/{self.pending_case.id}/",
            {"review_status": "accepted"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.pending_case.refresh_from_db()
        self.assertEqual(self.pending_case.review_status, "accepted")

    def test_non_staff_session_cannot_patch_review_status(self):
        """Non-staff user via session auth gets 403 on PATCH."""
        self.client.force_authenticate(user=self.regular_user)
        response = self.client.patch(
            f"/api/cases/{self.pending_case.id}/",
            {"review_status": "accepted"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    # ── PATCH unauthenticated ──

    def test_unauthenticated_cannot_patch(self):
        """Unauthenticated request gets 401 on PATCH."""
        response = self.client.patch(
            f"/api/cases/{self.pending_case.id}/",
            {"review_status": "accepted"},
            format="json",
        )
        self.assertIn(
            response.status_code,
            [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN],
        )

    # ── PUT (full update) same restrictions ──

    def test_non_staff_token_cannot_put(self):
        """Non-staff user gets 403 on PUT."""
        self.client.force_authenticate(user=self.regular_user, token=self.regular_token)
        response = self.client.put(
            f"/api/cases/{self.pending_case.id}/",
            {"review_status": "accepted"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    # ── Non-staff can still CREATE cases ──

    def test_non_staff_token_can_create_cases(self):
        """Non-staff user with cases:write can still POST new cases."""
        self.client.force_authenticate(user=self.regular_user, token=self.regular_token)
        data = {
            "court_name": self.court.name,
            "file_number": "NEW-CASE-999/24",
            "date": "2024-06-15",
            "content": "<p>New case content for creation test</p>",
        }
        response = self.client.post("/api/cases/", data, format="json")
        # Should succeed (201) or fail for non-permission reasons (not 403)
        self.assertNotEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    # ── Filter: review_status ──

    def test_filter_by_review_status_pending(self):
        """Staff user can filter cases by review_status=pending."""
        self.client.force_authenticate(user=self.staff_user, token=self.staff_token)
        response = self.client.get(
            "/api/cases/", {"review_status": "pending"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = [c["id"] for c in response.data["results"]]
        self.assertIn(self.pending_case.id, ids)
        self.assertNotIn(self.accepted_case.id, ids)

    def test_filter_by_review_status_accepted(self):
        """Filter by review_status=accepted returns only accepted cases."""
        self.client.force_authenticate(user=self.staff_user, token=self.staff_token)
        response = self.client.get(
            "/api/cases/", {"review_status": "accepted"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = [c["id"] for c in response.data["results"]]
        self.assertIn(self.accepted_case.id, ids)
        self.assertNotIn(self.pending_case.id, ids)

    # ── Filter: created_by_token ──

    def test_filter_by_created_by_token(self):
        """Staff user can filter cases by created_by_token."""
        self.client.force_authenticate(user=self.staff_user, token=self.staff_token)
        response = self.client.get(
            "/api/cases/",
            {"created_by_token": self.regular_token.id},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = [c["id"] for c in response.data["results"]]
        self.assertIn(self.pending_case.id, ids)
        self.assertNotIn(self.accepted_case.id, ids)

    # ── Visibility: non-staff sees only accepted + own ──

    def test_non_staff_sees_own_pending_and_accepted(self):
        """Non-staff user sees accepted cases + their own pending cases."""
        self.client.force_authenticate(user=self.regular_user, token=self.regular_token)
        response = self.client.get("/api/cases/", format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = [c["id"] for c in response.data["results"]]
        # Should see accepted case and their own pending case
        self.assertIn(self.accepted_case.id, ids)
        self.assertIn(self.pending_case.id, ids)

    def test_other_user_cannot_see_pending(self):
        """A different non-staff user cannot see another user's pending cases."""
        other_user = User.objects.create_user(
            username="other", email="other@example.com", password="testpass123"
        )
        other_group = APITokenPermissionGroup.objects.create(name="other_group")
        other_group.permissions.add(self.staff_read_perm)
        other_token = APIToken.objects.create(
            user=other_user,
            name="Other Token",
            permission_group=other_group,
        )
        self.client.force_authenticate(user=other_user, token=other_token)
        response = self.client.get("/api/cases/", format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = [c["id"] for c in response.data["results"]]
        # Should see accepted but not another user's pending
        self.assertIn(self.accepted_case.id, ids)
        self.assertNotIn(self.pending_case.id, ids)
