"""
Unit tests for the Case Creation API.

Tests cover:
- Successful case creation
- Court resolution from name
- Duplicate detection (409 Conflict)
- Validation errors
- Reference extraction (optional)
- API token tracking
- Authentication and permissions
"""

from datetime import date
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient, APITestCase

from oldp.apps.accounts.models import (
    APIToken,
    APITokenPermission,
    APITokenPermissionGroup,
)
from oldp.apps.cases.exceptions import CourtNotFoundError, DuplicateCaseError
from oldp.apps.cases.models import Case
from oldp.apps.cases.serializers import CaseCreateSerializer
from oldp.apps.cases.services import CaseCreator, CourtResolver
from oldp.apps.courts.models import Court

User = get_user_model()


class CourtResolverTestCase(TestCase):
    """Tests for the CourtResolver service."""

    fixtures = [
        "locations/countries.json",
        "locations/states.json",
        "locations/cities.json",
        "courts/courts.json",
    ]

    def setUp(self):
        self.resolver = CourtResolver()

    def test_remove_chamber_with_number(self):
        """Test chamber extraction with numbered chamber."""
        name = "LG Koblenz 14. Zivilkammer"
        result_name, chamber = self.resolver.remove_chamber(name)
        self.assertEqual(result_name, "LG Koblenz")
        self.assertIsNotNone(chamber)
        self.assertIn("14", chamber)

    def test_remove_chamber_senat(self):
        """Test chamber extraction with Senat designation."""
        name = "OLG Koblenz 2. Senat für Bußgeldsachen"
        result_name, chamber = self.resolver.remove_chamber(name)
        self.assertEqual(result_name, "OLG Koblenz")
        self.assertIsNotNone(chamber)

    def test_remove_chamber_no_chamber(self):
        """Test chamber extraction when no chamber present."""
        name = "Amtsgericht Berlin"
        result_name, chamber = self.resolver.remove_chamber(name)
        self.assertEqual(result_name, "Amtsgericht Berlin")
        self.assertIsNone(chamber)

    def test_find_court_by_code(self):
        """Test finding court by code."""
        # Assuming there's a court with code in fixtures
        courts = Court.objects.exclude(code="").exclude(code__isnull=True)
        if courts.exists():
            court = courts.first()
            found = self.resolver.find_court("", court.code)
            self.assertEqual(found.pk, court.pk)

    def test_find_court_not_found_raises_error(self):
        """Test that non-existent court raises CourtNotFoundError."""
        with self.assertRaises(CourtNotFoundError):
            self.resolver.find_court("Nonexistent Court XYZ 12345")

    def test_find_court_empty_name_raises_error(self):
        """Test that empty court name raises CourtNotFoundError."""
        with self.assertRaises(CourtNotFoundError):
            self.resolver.find_court("")

    def test_resolve_extracts_chamber(self):
        """Test that resolve method extracts chamber and finds court."""
        # Get a valid court from fixtures
        court = Court.objects.exclude(pk=Court.DEFAULT_ID).first()
        if court:
            # Mock find_court to return the court
            with patch.object(self.resolver, "find_court", return_value=court):
                found_court, chamber = self.resolver.resolve(
                    "LG Test 14. Zivilkammer"
                )
                self.assertEqual(found_court, court)


class CaseCreatorTestCase(TestCase):
    """Tests for the CaseCreator service."""

    fixtures = [
        "locations/countries.json",
        "locations/states.json",
        "locations/cities.json",
        "courts/courts.json",
    ]

    def setUp(self):
        self.creator = CaseCreator(extract_refs=False)
        self.court = Court.objects.exclude(pk=Court.DEFAULT_ID).first()

    def test_check_duplicate_returns_false_for_new_case(self):
        """Test duplicate check returns False for non-existent case."""
        result = self.creator.check_duplicate(self.court, "UNIQUE-FILE-123/99")
        self.assertFalse(result)

    def test_check_duplicate_returns_true_for_existing_case(self):
        """Test duplicate check returns True for existing case."""
        Case.objects.create(
            court=self.court,
            file_number="EXISTING-FILE-123/99",
            date=date(2021, 1, 1),
            content="<p>Test content</p>",
        )
        result = self.creator.check_duplicate(self.court, "EXISTING-FILE-123/99")
        self.assertTrue(result)

    def test_create_case_success(self):
        """Test successful case creation."""
        with patch.object(
            self.creator.court_resolver, "resolve", return_value=(self.court, None)
        ):
            case = self.creator.create_case(
                court_name=self.court.name,
                file_number="NEW-FILE-456/21",
                date=date(2021, 5, 15),
                content="<p>Case content</p>",
                case_type="Urteil",
            )

            self.assertIsNotNone(case.pk)
            self.assertEqual(case.court, self.court)
            self.assertEqual(case.file_number, "NEW-FILE-456/21")
            self.assertEqual(case.type, "Urteil")
            self.assertIsNotNone(case.slug)

    def test_create_case_duplicate_raises_error(self):
        """Test that creating duplicate case raises DuplicateCaseError."""
        # Create initial case
        Case.objects.create(
            court=self.court,
            file_number="DUP-FILE-789/21",
            date=date(2021, 1, 1),
            content="<p>Original content</p>",
        )

        with patch.object(
            self.creator.court_resolver, "resolve", return_value=(self.court, None)
        ):
            with self.assertRaises(DuplicateCaseError):
                self.creator.create_case(
                    court_name=self.court.name,
                    file_number="DUP-FILE-789/21",
                    date=date(2021, 5, 15),
                    content="<p>Duplicate content</p>",
                )

    def test_create_case_with_api_token_tracking(self):
        """Test that API token is tracked on created case."""
        user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass123"
        )
        token = APIToken.objects.create(user=user, name="Test Token")

        with patch.object(
            self.creator.court_resolver, "resolve", return_value=(self.court, None)
        ):
            case = self.creator.create_case(
                court_name=self.court.name,
                file_number="TOKEN-FILE-111/21",
                date=date(2021, 5, 15),
                content="<p>Case content</p>",
                api_token=token,
            )

            self.assertEqual(case.created_by_token, token)
            # Cases created with API token are private (require approval)
            self.assertTrue(case.private)

    def test_create_case_sets_slug(self):
        """Test that slug is set correctly on created case."""
        with patch.object(
            self.creator.court_resolver, "resolve", return_value=(self.court, None)
        ):
            case = self.creator.create_case(
                court_name=self.court.name,
                file_number="SLUG-TEST-222/21",
                date=date(2021, 5, 15),
                content="<p>Case content</p>",
            )

            self.assertIsNotNone(case.slug)
            self.assertIn(self.court.slug, case.slug)
            self.assertIn("2021-05-15", case.slug)


class CaseCreateSerializerTestCase(TestCase):
    """Tests for the CaseCreateSerializer."""

    def test_valid_data(self):
        """Test serializer with valid data."""
        data = {
            "court_name": "Bundesgerichtshof",
            "file_number": "I ZR 123/21",
            "date": "2021-05-15",
            "content": "<p>Case content with sufficient length</p>",
            "type": "Urteil",
        }
        serializer = CaseCreateSerializer(data=data)
        self.assertTrue(serializer.is_valid(), serializer.errors)

    def test_missing_required_field(self):
        """Test serializer rejects missing required fields."""
        data = {
            "court_name": "Bundesgerichtshof",
            # Missing file_number, date, content
        }
        serializer = CaseCreateSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn("file_number", serializer.errors)
        self.assertIn("date", serializer.errors)
        self.assertIn("content", serializer.errors)

    def test_empty_court_name_rejected(self):
        """Test serializer rejects empty court name."""
        data = {
            "court_name": "",
            "file_number": "I ZR 123/21",
            "date": "2021-05-15",
            "content": "<p>Case content</p>",
        }
        serializer = CaseCreateSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn("court_name", serializer.errors)

    def test_content_too_short(self):
        """Test serializer rejects content that is too short."""
        data = {
            "court_name": "Bundesgerichtshof",
            "file_number": "I ZR 123/21",
            "date": "2021-05-15",
            "content": "short",  # Less than 10 characters
        }
        serializer = CaseCreateSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn("content", serializer.errors)

    @override_settings(CASE_CREATION_VALIDATION={"content_min_length": 5})
    def test_content_validation_uses_settings(self):
        """Test that content validation respects settings."""
        data = {
            "court_name": "Bundesgerichtshof",
            "file_number": "I ZR 123/21",
            "date": "2021-05-15",
            "content": "12345",  # Exactly 5 characters
        }
        serializer = CaseCreateSerializer(data=data)
        self.assertTrue(serializer.is_valid(), serializer.errors)



class CaseCreationAPITestCase(APITestCase):
    """Integration tests for the Case Creation API endpoint."""

    fixtures = [
        "locations/countries.json",
        "locations/states.json",
        "locations/cities.json",
        "courts/courts.json",
    ]

    def setUp(self):
        # Create user
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass123"
        )

        # Create permission and permission group for write access
        self.write_permission, _ = APITokenPermission.objects.get_or_create(
            resource="cases", action="write"
        )
        self.permission_group = APITokenPermissionGroup.objects.create(
            name="test_write_group"
        )
        self.permission_group.permissions.add(self.write_permission)

        # Create API token with write permission
        self.token = APIToken.objects.create(
            user=self.user,
            name="Test Token",
            permission_group=self.permission_group,
        )

        self.client = APIClient()
        # Use force_authenticate to set both user and token (request.auth)
        self.client.force_authenticate(user=self.user, token=self.token)

        # Get a valid court for testing
        self.court = Court.objects.exclude(pk=Court.DEFAULT_ID).first()

    def _get_valid_case_data(self, file_number=None):
        """Helper to get valid case creation data."""
        return {
            "court_name": self.court.name,
            "file_number": file_number or "TEST-FILE-123/21",
            "date": "2021-05-15",
            "content": "<p>Test case content with sufficient length for validation</p>",
            "type": "Urteil",
        }

    @patch("oldp.apps.cases.services.case_creator.CaseCreator.create_case")
    def test_create_case_success(self, mock_create):
        """Test successful case creation returns 201 with id and slug."""
        mock_case = MagicMock()
        mock_case.id = 12345
        mock_case.slug = "test-court-2021-05-15-test-file-123-21"
        mock_create.return_value = mock_case

        data = self._get_valid_case_data()
        response = self.client.post("/api/cases/", data, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn("id", response.data)
        self.assertIn("slug", response.data)

    @patch("oldp.apps.cases.services.case_creator.CaseCreator.create_case")
    def test_create_case_duplicate_returns_409(self, mock_create):
        """Test duplicate case returns 409 Conflict."""
        mock_create.side_effect = DuplicateCaseError(
            "A case with this court and file number already exists."
        )

        data = self._get_valid_case_data()
        response = self.client.post("/api/cases/", data, format="json")

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)

    @patch("oldp.apps.cases.services.case_creator.CaseCreator.create_case")
    def test_create_case_court_not_found_returns_400(self, mock_create):
        """Test court not found returns 400 Bad Request."""
        mock_create.side_effect = CourtNotFoundError(
            "Could not resolve court from name."
        )

        data = self._get_valid_case_data()
        data["court_name"] = "Nonexistent Court XYZ 12345"
        response = self.client.post("/api/cases/", data, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_case_missing_required_fields_returns_400(self):
        """Test missing required fields returns 400 Bad Request."""
        data = {"court_name": "Test Court"}  # Missing other required fields
        response = self.client.post("/api/cases/", data, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("file_number", response.data)
        self.assertIn("date", response.data)
        self.assertIn("content", response.data)

    def test_create_case_without_authentication_returns_401(self):
        """Test unauthenticated request returns 401."""
        # Clear authentication
        self.client.force_authenticate(user=None, token=None)
        data = self._get_valid_case_data()
        response = self.client.post("/api/cases/", data, format="json")

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_create_case_without_write_permission_returns_403(self):
        """Test request without write permission returns 403."""
        # Create token without write permission
        read_permission, _ = APITokenPermission.objects.get_or_create(
            resource="cases", action="read"
        )
        read_only_group = APITokenPermissionGroup.objects.create(name="read_only_group")
        read_only_group.permissions.add(read_permission)

        read_only_token = APIToken.objects.create(
            user=self.user, name="Read Only Token", permission_group=read_only_group
        )

        # Use force_authenticate with the read-only token
        self.client.force_authenticate(user=self.user, token=read_only_token)

        data = self._get_valid_case_data()
        response = self.client.post("/api/cases/", data, format="json")

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    @patch("oldp.apps.cases.services.case_creator.CaseCreator.create_case")
    def test_create_case_tracks_api_token(self, mock_create):
        """Test that API token is passed to case creator."""
        mock_case = MagicMock()
        mock_case.id = 12345
        mock_case.slug = "test-slug"
        mock_create.return_value = mock_case

        data = self._get_valid_case_data()
        self.client.post("/api/cases/", data, format="json")

        # Verify create_case was called with api_token
        mock_create.assert_called_once()
        call_kwargs = mock_create.call_args[1]
        self.assertEqual(call_kwargs["api_token"], self.token)

    def test_create_case_content_too_short_returns_400(self):
        """Test content validation returns 400 for short content."""
        data = self._get_valid_case_data()
        data["content"] = "short"  # Less than minimum length
        response = self.client.post("/api/cases/", data, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("content", response.data)

    @patch("oldp.apps.cases.services.case_creator.CaseCreator.create_case")
    def test_create_case_with_all_optional_fields(self, mock_create):
        """Test case creation with all optional fields."""
        mock_case = MagicMock()
        mock_case.id = 12345
        mock_case.slug = "test-slug"
        mock_create.return_value = mock_case

        data = self._get_valid_case_data()
        data.update(
            {
                "ecli": "ECLI:DE:BGH:2021:150521UTEST123.21.0",
                "abstract": "<p>Case abstract summary</p>",
                "title": "Test Case Title",
                "private": True,
            }
        )

        response = self.client.post("/api/cases/", data, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        # Verify all fields were passed to create_case
        call_kwargs = mock_create.call_args[1]
        self.assertEqual(call_kwargs["ecli"], data["ecli"])
        self.assertEqual(call_kwargs["abstract"], data["abstract"])
        self.assertEqual(call_kwargs["title"], data["title"])
        self.assertTrue(call_kwargs["private"])

    @patch("oldp.apps.cases.services.case_creator.CaseCreator.create_case")
    def test_create_case_extract_refs_disabled_via_query_param(self, mock_create):
        """Test that extract_refs can be disabled via query parameter."""
        mock_case = MagicMock()
        mock_case.id = 12345
        mock_case.slug = "test-slug"
        mock_create.return_value = mock_case

        data = self._get_valid_case_data()

        # Use query parameter to disable extract_refs
        self.client.post("/api/cases/?extract_refs=false", data, format="json")

        call_kwargs = mock_create.call_args[1]
        self.assertFalse(call_kwargs["extract_refs"])

    @patch("oldp.apps.cases.services.case_creator.CaseCreator.create_case")
    def test_create_case_extract_refs_enabled_by_default(self, mock_create):
        """Test that extract_refs is enabled by default."""
        mock_case = MagicMock()
        mock_case.id = 12345
        mock_case.slug = "test-slug"
        mock_create.return_value = mock_case

        data = self._get_valid_case_data()

        self.client.post("/api/cases/", data, format="json")

        call_kwargs = mock_create.call_args[1]
        self.assertTrue(call_kwargs["extract_refs"])

    @patch("oldp.apps.cases.services.case_creator.CaseCreator.create_case")
    def test_create_case_extract_refs_query_param_variations(self, mock_create):
        """Test various values for extract_refs query parameter."""
        mock_case = MagicMock()
        mock_case.id = 12345
        mock_case.slug = "test-slug"
        mock_create.return_value = mock_case

        data = self._get_valid_case_data()

        # Test "0" disables
        self.client.post("/api/cases/?extract_refs=0", data, format="json")
        self.assertFalse(mock_create.call_args[1]["extract_refs"])

        # Test "no" disables
        mock_create.reset_mock()
        self.client.post("/api/cases/?extract_refs=no", data, format="json")
        self.assertFalse(mock_create.call_args[1]["extract_refs"])

        # Test "true" enables
        mock_create.reset_mock()
        self.client.post("/api/cases/?extract_refs=true", data, format="json")
        self.assertTrue(mock_create.call_args[1]["extract_refs"])


class CaseCreationIntegrationTestCase(APITestCase):
    """
    Full integration tests for case creation without mocking.

    These tests verify the complete flow from API to database.
    """

    fixtures = [
        "locations/countries.json",
        "locations/states.json",
        "locations/cities.json",
        "courts/courts.json",
    ]

    def setUp(self):
        self.user = User.objects.create_user(
            username="integrationuser", email="integration@example.com", password="testpass"
        )

        write_permission, _ = APITokenPermission.objects.get_or_create(
            resource="cases", action="write"
        )
        permission_group = APITokenPermissionGroup.objects.create(
            name="integration_write_group"
        )
        permission_group.permissions.add(write_permission)

        self.token = APIToken.objects.create(
            user=self.user, name="Integration Token", permission_group=permission_group
        )

        self.client = APIClient()
        # Use force_authenticate to set both user and token (request.auth)
        self.client.force_authenticate(user=self.user, token=self.token)

        self.court = Court.objects.exclude(pk=Court.DEFAULT_ID).first()

    def test_full_case_creation_flow(self):
        """Test complete case creation from API to database."""
        data = {
            "court_name": self.court.name,
            "file_number": "INTEGRATION-TEST-999/21",
            "date": "2021-05-15",
            "content": "<p>Integration test case content with references to § 823 BGB</p>",
            "type": "Urteil",
        }

        # Use query param to disable ref extraction for faster test
        response = self.client.post("/api/cases/?extract_refs=false", data, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        # Verify case was created in database
        case_id = response.data["id"]
        case = Case.objects.get(pk=case_id)

        self.assertEqual(case.court, self.court)
        self.assertEqual(case.file_number, "INTEGRATION-TEST-999/21")
        self.assertEqual(str(case.date), "2021-05-15")
        self.assertEqual(case.type, "Urteil")
        self.assertEqual(case.created_by_token, self.token)
        self.assertIsNotNone(case.slug)
        # API-created cases require manual approval (private=True)
        self.assertTrue(case.private)

    def test_api_created_cases_are_private_by_default(self):
        """Test that cases created via API are always private (require approval)."""
        data = {
            "court_name": self.court.name,
            "file_number": "PRIVATE-TEST-777/21",
            "date": "2021-05-15",
            "content": "<p>Test case content</p>",
            "private": False,  # Explicitly try to set public
        }

        response = self.client.post("/api/cases/?extract_refs=false", data, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        # Verify case is private despite request setting private=False
        case = Case.objects.get(pk=response.data["id"])
        self.assertTrue(case.private, "API-created cases must be private for approval workflow")

    def test_duplicate_case_prevention(self):
        """Test that duplicate cases are prevented."""
        data = {
            "court_name": self.court.name,
            "file_number": "DUPLICATE-TEST-888/21",
            "date": "2021-05-15",
            "content": "<p>First case content</p>",
        }

        # Create first case (disable ref extraction for faster test)
        response1 = self.client.post("/api/cases/?extract_refs=false", data, format="json")
        self.assertEqual(response1.status_code, status.HTTP_201_CREATED)

        # Try to create duplicate
        response2 = self.client.post("/api/cases/?extract_refs=false", data, format="json")
        self.assertEqual(response2.status_code, status.HTTP_409_CONFLICT)

        # Verify only one case exists
        count = Case.objects.filter(
            court=self.court, file_number="DUPLICATE-TEST-888/21"
        ).count()
        self.assertEqual(count, 1)
