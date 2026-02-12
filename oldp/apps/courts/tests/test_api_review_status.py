"""Tests for review_status-based filtering and visibility in the Court API."""

from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APIClient, APITestCase

from oldp.apps.accounts.models import (
    APIToken,
    APITokenPermission,
    APITokenPermissionGroup,
)
from oldp.apps.courts.models import Court, State

User = get_user_model()


class CourtReviewStatusAPITestCase(APITestCase):
    """Tests for review_status filtering and field visibility on the Court API."""

    fixtures = [
        "locations/countries.json",
        "locations/states.json",
        "locations/cities.json",
        "courts/courts.json",
    ]

    def setUp(self):
        self.state = State.objects.first()

        # Users and tokens
        self.user_a = User.objects.create_user(
            username="court_user_a", email="court_a@example.com", password="pass"
        )
        read_perm, _ = APITokenPermission.objects.get_or_create(
            resource="courts", action="read"
        )
        group = APITokenPermissionGroup.objects.create(name="courts_read")
        group.permissions.add(read_perm)
        self.token_a = APIToken.objects.create(
            user=self.user_a, name="Token A", permission_group=group
        )

        self.user_b = User.objects.create_user(
            username="court_user_b", email="court_b@example.com", password="pass"
        )
        self.token_b = APIToken.objects.create(
            user=self.user_b, name="Token B", permission_group=group
        )

        self.staff_user = User.objects.create_user(
            username="court_staff",
            email="court_staff@example.com",
            password="pass",
            is_staff=True,
        )
        self.token_staff = APIToken.objects.create(
            user=self.staff_user, name="Token Staff", permission_group=group
        )

        # Existing courts from fixtures are all accepted.
        # Create pending courts for test.
        self.pending_court_a = Court.objects.create(
            name="Pending Court A",
            code="PCTSTA",
            slug="pending-court-a",
            state=self.state,
            review_status="pending",
            created_by_token=self.token_a,
        )
        self.pending_court_b = Court.objects.create(
            name="Pending Court B",
            code="PCTSTB",
            slug="pending-court-b",
            state=self.state,
            review_status="pending",
            created_by_token=self.token_b,
        )

        # Pick one accepted court from fixtures
        self.accepted_court = (
            Court.objects.filter(review_status="accepted")
            .exclude(pk__in=[self.pending_court_a.pk, self.pending_court_b.pk])
            .first()
        )

        self.client = APIClient()

    def _get_ids(self, response):
        return {item["id"] for item in response.data["results"]}

    def test_list_returns_accepted_and_own_for_regular_user(self):
        """Regular user sees accepted courts + their own pending courts."""
        self.client.force_authenticate(user=self.user_a, token=self.token_a)
        response = self.client.get("/api/courts/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = self._get_ids(response)
        self.assertIn(self.accepted_court.pk, ids)
        self.assertIn(self.pending_court_a.pk, ids)
        self.assertNotIn(self.pending_court_b.pk, ids)

    def test_list_staff_sees_all(self):
        """Staff user sees all courts."""
        self.client.force_authenticate(user=self.staff_user, token=self.token_staff)
        response = self.client.get("/api/courts/")

        ids = self._get_ids(response)
        self.assertIn(self.accepted_court.pk, ids)
        self.assertIn(self.pending_court_a.pk, ids)
        self.assertIn(self.pending_court_b.pk, ids)

    def test_detail_returns_404_for_others_pending(self):
        """Non-owner cannot access another user's pending court."""
        self.client.force_authenticate(user=self.user_b, token=self.token_b)
        response = self.client.get(f"/api/courts/{self.pending_court_a.pk}/")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_detail_owner_can_access_pending(self):
        """Owner can access their own pending court."""
        self.client.force_authenticate(user=self.user_a, token=self.token_a)
        response = self.client.get(f"/api/courts/{self.pending_court_a.pk}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_detail_staff_can_access_pending(self):
        """Staff can access any pending court."""
        self.client.force_authenticate(user=self.staff_user, token=self.token_staff)
        response = self.client.get(f"/api/courts/{self.pending_court_a.pk}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_review_status_hidden_for_non_owner(self):
        """review_status is hidden for non-owner users."""
        self.client.force_authenticate(user=self.user_b, token=self.token_b)
        response = self.client.get(f"/api/courts/{self.accepted_court.pk}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertNotIn("review_status", response.data)

    def test_review_status_visible_for_owner(self):
        """Owner sees review_status on their own court."""
        self.client.force_authenticate(user=self.user_a, token=self.token_a)
        response = self.client.get(f"/api/courts/{self.pending_court_a.pk}/")
        self.assertIn("review_status", response.data)
        self.assertEqual(response.data["review_status"], "pending")

    def test_review_status_visible_for_staff(self):
        """Staff sees review_status on all courts."""
        self.client.force_authenticate(user=self.staff_user, token=self.token_staff)
        response = self.client.get(f"/api/courts/{self.accepted_court.pk}/")
        self.assertIn("review_status", response.data)
