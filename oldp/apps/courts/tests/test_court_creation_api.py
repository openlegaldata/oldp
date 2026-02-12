"""Unit tests for the Court Creation API.

Tests cover:
- Successful court creation
- Duplicate detection
- State resolution
- City resolution (creates city if missing)
- API token tracking
- Review status management
- Authentication and permissions
"""

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient, APITestCase

from oldp.apps.accounts.models import (
    APIToken,
    APITokenPermission,
    APITokenPermissionGroup,
)
from oldp.apps.courts.exceptions import DuplicateCourtError, StateNotFoundError
from oldp.apps.courts.models import City, Country, Court, State
from oldp.apps.courts.services import CourtCreator

User = get_user_model()


class CourtCreatorTestCase(TestCase):
    """Tests for the CourtCreator service."""

    def setUp(self):
        self.creator = CourtCreator()
        self.country = Country.objects.create(name="Deutschland", code="de")
        self.state = State.objects.create(
            name="Berlin", country=self.country, slug="berlin"
        )
        self.city = City.objects.create(name="Berlin", state=self.state)

    def test_create_court_success(self):
        """Test successful court creation."""
        court = self.creator.create_court(
            name="Amtsgericht Berlin-Mitte",
            code="AGBERLINMITTE",
            state_name="Berlin",
            court_type="AG",
            city_name="Berlin",
        )

        self.assertIsNotNone(court.pk)
        self.assertEqual(court.name, "Amtsgericht Berlin-Mitte")
        self.assertEqual(court.code, "AGBERLINMITTE")
        self.assertEqual(court.state, self.state)
        self.assertEqual(court.city, self.city)
        self.assertEqual(court.court_type, "AG")
        self.assertEqual(court.review_status, "accepted")

    def test_create_court_duplicate_raises_error(self):
        """Test that creating duplicate court raises DuplicateCourtError."""
        self.creator.create_court(
            name="Amtsgericht Berlin-Mitte",
            code="AGBERLIN",
            state_name="Berlin",
        )

        with self.assertRaises(DuplicateCourtError):
            self.creator.create_court(
                name="Amtsgericht Berlin-Mitte 2",
                code="AGBERLIN",
                state_name="Berlin",
            )

    def test_resolve_state(self):
        """Test state resolution by name."""
        state = self.creator.resolve_state("Berlin")
        self.assertEqual(state, self.state)

    def test_resolve_state_case_insensitive(self):
        """Test state resolution is case-insensitive."""
        state = self.creator.resolve_state("berlin")
        self.assertEqual(state, self.state)

    def test_resolve_state_not_found_raises_error(self):
        """Test that non-existent state raises StateNotFoundError."""
        with self.assertRaises(StateNotFoundError):
            self.creator.resolve_state("NonExistentState")

    def test_resolve_city_existing(self):
        """Test resolving an existing city."""
        city = self.creator.resolve_city("Berlin", self.state)
        self.assertEqual(city, self.city)

    def test_resolve_city_creates_if_missing(self):
        """Test that city is created if not found."""
        city = self.creator.resolve_city("Spandau", self.state)
        self.assertIsNotNone(city)
        self.assertEqual(city.name, "Spandau")
        self.assertEqual(city.state, self.state)

    def test_resolve_city_returns_none_if_empty(self):
        """Test that empty city name returns None."""
        city = self.creator.resolve_city("", self.state)
        self.assertIsNone(city)

    def test_create_court_with_api_token_tracking(self):
        """Test that API token is tracked on created court."""
        user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass123"
        )
        token = APIToken.objects.create(user=user, name="Test Token")

        court = self.creator.create_court(
            name="Amtsgericht Test",
            code="AGTEST",
            state_name="Berlin",
            api_token=token,
        )

        self.assertEqual(court.created_by_token, token)

    def test_review_status_pending_when_api_token_set(self):
        """Test that review_status is 'pending' when api_token is provided."""
        user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass123"
        )
        token = APIToken.objects.create(user=user, name="Test Token")

        court = self.creator.create_court(
            name="Amtsgericht Pending",
            code="AGPEND",
            state_name="Berlin",
            api_token=token,
        )

        self.assertEqual(court.review_status, "pending")

    def test_review_status_accepted_without_api_token(self):
        """Test that review_status is 'accepted' without api_token."""
        court = self.creator.create_court(
            name="Amtsgericht Accepted",
            code="AGACC",
            state_name="Berlin",
        )

        self.assertEqual(court.review_status, "accepted")

    def test_create_court_without_city(self):
        """Test creating court without city (state-level court)."""
        court = self.creator.create_court(
            name="Bundesgerichtshof",
            code="BGH",
            state_name="Berlin",
        )

        self.assertIsNotNone(court.pk)
        self.assertIsNone(court.city)


class CourtCreationAPITestCase(APITestCase):
    """Integration tests for the Court Creation API endpoint."""

    def setUp(self):
        # Create reference data
        self.country = Country.objects.create(name="Deutschland", code="de")
        self.state = State.objects.create(
            name="Berlin", country=self.country, slug="berlin"
        )
        self.city = City.objects.create(name="Berlin", state=self.state)

        # Create user
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass123"
        )

        # Create permission and permission group for write access
        self.write_permission, _ = APITokenPermission.objects.get_or_create(
            resource="courts", action="write"
        )
        self.permission_group = APITokenPermissionGroup.objects.create(
            name="courts_write_group"
        )
        self.permission_group.permissions.add(self.write_permission)

        # Create API token with write permission
        self.token = APIToken.objects.create(
            user=self.user,
            name="Test Token",
            permission_group=self.permission_group,
        )

        self.client = APIClient()
        self.client.force_authenticate(user=self.user, token=self.token)

    def test_create_court_success(self):
        """Test successful court creation via API."""
        data = {
            "name": "Amtsgericht Berlin-Mitte",
            "code": "AGBERLINMITTE",
            "state_name": "Berlin",
            "court_type": "AG",
            "city_name": "Berlin",
        }

        response = self.client.post("/api/courts/", data, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn("id", response.data)
        self.assertIn("slug", response.data)
        self.assertIn("review_status", response.data)
        self.assertEqual(response.data["review_status"], "pending")

    def test_create_court_duplicate_returns_409(self):
        """Test duplicate court returns 409 Conflict."""
        Court.objects.create(
            name="Existing Court",
            code="EXISTING",
            state=self.state,
            slug="existing",
        )

        data = {
            "name": "Another Court",
            "code": "EXISTING",
            "state_name": "Berlin",
        }

        response = self.client.post("/api/courts/", data, format="json")

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)

    def test_create_court_state_not_found_returns_400(self):
        """Test court creation with non-existent state returns 400."""
        data = {
            "name": "Test Court",
            "code": "TESTCOURT",
            "state_name": "NonExistentState",
        }

        response = self.client.post("/api/courts/", data, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_court_without_authentication_returns_401(self):
        """Test unauthenticated request returns 401."""
        self.client.force_authenticate(user=None, token=None)

        data = {
            "name": "No Auth Court",
            "code": "NOAUTH",
            "state_name": "Berlin",
        }

        response = self.client.post("/api/courts/", data, format="json")

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_create_court_tracks_api_token(self):
        """Test that API token is tracked on created court."""
        data = {
            "name": "Token Court",
            "code": "TOKENCOURT",
            "state_name": "Berlin",
        }

        response = self.client.post("/api/courts/", data, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        # Verify token was tracked
        court = Court.objects.get(pk=response.data["id"])
        self.assertEqual(court.created_by_token, self.token)

    def test_create_court_review_status_pending(self):
        """Test that API-created courts have review_status='pending'."""
        data = {
            "name": "Pending Court",
            "code": "PENDCOURT",
            "state_name": "Berlin",
        }

        response = self.client.post("/api/courts/", data, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["review_status"], "pending")

        court = Court.objects.get(pk=response.data["id"])
        self.assertEqual(court.review_status, "pending")

    def test_create_court_missing_required_fields_returns_400(self):
        """Test missing required fields returns 400."""
        data = {
            "name": "Incomplete Court",
            # Missing code and state_name
        }

        response = self.client.post("/api/courts/", data, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("code", response.data)
        self.assertIn("state_name", response.data)

    def test_read_courts_still_works(self):
        """Test that GET /api/courts/ still works."""
        # Add read permission to the token's group
        read_permission, _ = APITokenPermission.objects.get_or_create(
            resource="courts", action="read"
        )
        self.permission_group.permissions.add(read_permission)

        Court.objects.create(
            name="Test Court",
            code="TESTREAD",
            state=self.state,
            slug="testread",
        )

        response = self.client.get("/api/courts/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
