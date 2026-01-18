"""
Unit tests for the Law and LawBook Creation API.

Tests cover:
- Successful law book creation
- Revision/latest flag management
- Duplicate detection
- Law creation within books
- Book resolution from code
- API token tracking
- Authentication and permissions
"""

from datetime import date
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient, APITestCase

from oldp.apps.accounts.models import (
    APIToken,
    APITokenPermission,
    APITokenPermissionGroup,
)
from oldp.apps.laws.exceptions import (
    DuplicateLawBookError,
    DuplicateLawError,
    LawBookNotFoundError,
)
from oldp.apps.laws.models import Law, LawBook
from oldp.apps.laws.services import LawBookCreator, LawCreator

User = get_user_model()


class LawBookCreatorTestCase(TestCase):
    """Tests for the LawBookCreator service."""

    def setUp(self):
        self.creator = LawBookCreator()

    def test_create_lawbook_success(self):
        """Test successful law book creation."""
        lawbook = self.creator.create_lawbook(
            code="TESTBUCH",
            title="Testgesetzbuch",
            revision_date=date(2021, 1, 1),
        )

        self.assertIsNotNone(lawbook.pk)
        self.assertEqual(lawbook.code, "TESTBUCH")
        self.assertEqual(lawbook.title, "Testgesetzbuch")
        self.assertEqual(lawbook.slug, "testbuch")
        self.assertTrue(lawbook.latest)

    def test_create_lawbook_duplicate_raises_error(self):
        """Test that creating duplicate law book raises DuplicateLawBookError."""
        # Create initial law book
        self.creator.create_lawbook(
            code="DUPBOOK",
            title="Duplicate Book",
            revision_date=date(2021, 1, 1),
        )

        # Try to create duplicate
        with self.assertRaises(DuplicateLawBookError):
            self.creator.create_lawbook(
                code="DUPBOOK",
                title="Duplicate Book 2",
                revision_date=date(2021, 1, 1),  # Same revision date
            )

    def test_create_newer_revision_becomes_latest(self):
        """Test that creating a newer revision becomes the latest."""
        # Create older revision
        old_book = self.creator.create_lawbook(
            code="REVBOOK",
            title="Revision Book Old",
            revision_date=date(2020, 1, 1),
        )
        self.assertTrue(old_book.latest)

        # Create newer revision
        new_book = self.creator.create_lawbook(
            code="REVBOOK",
            title="Revision Book New",
            revision_date=date(2021, 1, 1),
        )

        # Refresh old book from database
        old_book.refresh_from_db()

        # New book should be latest
        self.assertTrue(new_book.latest)
        # Old book should no longer be latest
        self.assertFalse(old_book.latest)

    def test_create_older_revision_not_latest(self):
        """Test that creating an older revision does not become latest."""
        # Create newer revision first
        new_book = self.creator.create_lawbook(
            code="OLDREVBOOK",
            title="Older Revision Book New",
            revision_date=date(2021, 1, 1),
        )
        self.assertTrue(new_book.latest)

        # Create older revision
        old_book = self.creator.create_lawbook(
            code="OLDREVBOOK",
            title="Older Revision Book Old",
            revision_date=date(2020, 1, 1),
        )

        # Refresh new book from database
        new_book.refresh_from_db()

        # Old book should not be latest
        self.assertFalse(old_book.latest)
        # New book should still be latest
        self.assertTrue(new_book.latest)

    def test_create_lawbook_with_api_token_tracking(self):
        """Test that API token is tracked on created law book."""
        user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass123"
        )
        token = APIToken.objects.create(user=user, name="Test Token")

        lawbook = self.creator.create_lawbook(
            code="TOKENBOOK",
            title="Token Book",
            revision_date=date(2021, 1, 1),
            api_token=token,
        )

        self.assertEqual(lawbook.created_by_token, token)


class LawCreatorTestCase(TestCase):
    """Tests for the LawCreator service."""

    def setUp(self):
        self.creator = LawCreator()
        # Create a law book for testing
        self.lawbook = LawBook.objects.create(
            code="TESTLAW",
            title="Test Law Book",
            slug="testlaw",
            revision_date=date(2021, 1, 1),
            latest=True,
        )

    def test_create_law_success(self):
        """Test successful law creation."""
        law = self.creator.create_law(
            book_code="TESTLAW",
            section="§ 1",
            title="Test Section",
            content="<p>Test content</p>",
        )

        self.assertIsNotNone(law.pk)
        self.assertEqual(law.book, self.lawbook)
        self.assertEqual(law.section, "§ 1")
        self.assertEqual(law.title, "Test Section")
        self.assertEqual(law.slug, "1")  # Auto-generated from section

    def test_create_law_with_custom_slug(self):
        """Test law creation with custom slug."""
        law = self.creator.create_law(
            book_code="TESTLAW",
            section="§ 2",
            title="Custom Slug Section",
            content="<p>Test content</p>",
            slug="custom-slug",
        )

        self.assertEqual(law.slug, "custom-slug")

    def test_create_law_duplicate_raises_error(self):
        """Test that creating duplicate law raises DuplicateLawError."""
        # Create initial law
        self.creator.create_law(
            book_code="TESTLAW",
            section="§ 99",
            title="Original Law",
            content="<p>Original content</p>",
        )

        # Try to create duplicate (same book and slug)
        with self.assertRaises(DuplicateLawError):
            self.creator.create_law(
                book_code="TESTLAW",
                section="§ 99",  # Same section, generates same slug
                title="Duplicate Law",
                content="<p>Duplicate content</p>",
            )

    def test_create_law_book_not_found_raises_error(self):
        """Test that non-existent book raises LawBookNotFoundError."""
        with self.assertRaises(LawBookNotFoundError):
            self.creator.create_law(
                book_code="NONEXISTENT",
                section="§ 1",
                title="Test",
                content="<p>Test</p>",
            )

    def test_create_law_with_specific_revision(self):
        """Test law creation with specific book revision."""
        # Create an older revision
        old_book = LawBook.objects.create(
            code="TESTLAW",
            title="Test Law Book Old",
            slug="testlaw",
            revision_date=date(2020, 1, 1),
            latest=False,
        )

        # Create law in the old revision
        law = self.creator.create_law(
            book_code="TESTLAW",
            section="§ 100",
            title="Old Revision Law",
            content="<p>Old content</p>",
            revision_date=date(2020, 1, 1),
        )

        self.assertEqual(law.book, old_book)

    def test_create_law_with_api_token_tracking(self):
        """Test that API token is tracked on created law."""
        user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass123"
        )
        token = APIToken.objects.create(user=user, name="Test Token")

        law = self.creator.create_law(
            book_code="TESTLAW",
            section="§ 200",
            title="Token Law",
            content="<p>Token content</p>",
            api_token=token,
        )

        self.assertEqual(law.created_by_token, token)

    def test_resolve_lawbook_by_code_latest(self):
        """Test resolving law book by code (uses latest)."""
        book = self.creator.resolve_lawbook("TESTLAW")
        self.assertEqual(book, self.lawbook)

    def test_resolve_lawbook_by_code_and_date(self):
        """Test resolving law book by code and specific date."""
        book = self.creator.resolve_lawbook("TESTLAW", revision_date=date(2021, 1, 1))
        self.assertEqual(book, self.lawbook)


class LawBookCreationAPITestCase(APITestCase):
    """Integration tests for the LawBook Creation API endpoint."""

    def setUp(self):
        # Create user
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass123"
        )

        # Create permission and permission group for write access
        self.write_permission, _ = APITokenPermission.objects.get_or_create(
            resource="lawbooks", action="write"
        )
        self.permission_group = APITokenPermissionGroup.objects.create(
            name="lawbooks_write_group"
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

    def test_create_lawbook_success(self):
        """Test successful law book creation via API."""
        data = {
            "code": "APIBOOK",
            "title": "API Created Book",
            "revision_date": "2021-05-15",
        }

        response = self.client.post("/api/law_books/", data, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn("id", response.data)
        self.assertIn("slug", response.data)
        self.assertIn("latest", response.data)
        self.assertTrue(response.data["latest"])

    def test_create_lawbook_duplicate_returns_409(self):
        """Test duplicate law book returns 409 Conflict."""
        # Create first law book
        LawBook.objects.create(
            code="DUPAPI",
            title="Duplicate API Book",
            slug="dupapi",
            revision_date=date(2021, 1, 1),
        )

        data = {
            "code": "DUPAPI",
            "title": "Duplicate API Book 2",
            "revision_date": "2021-01-01",
        }

        response = self.client.post("/api/law_books/", data, format="json")

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)

    def test_create_lawbook_without_authentication_returns_401(self):
        """Test unauthenticated request returns 401."""
        self.client.force_authenticate(user=None, token=None)

        data = {
            "code": "NOAUTH",
            "title": "No Auth Book",
            "revision_date": "2021-01-01",
        }

        response = self.client.post("/api/law_books/", data, format="json")

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_create_lawbook_tracks_api_token(self):
        """Test that API token is tracked on created law book."""
        data = {
            "code": "TOKENAPI",
            "title": "Token API Book",
            "revision_date": "2021-05-15",
        }

        response = self.client.post("/api/law_books/", data, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        # Verify token was tracked
        lawbook = LawBook.objects.get(pk=response.data["id"])
        self.assertEqual(lawbook.created_by_token, self.token)


class LawCreationAPITestCase(APITestCase):
    """Integration tests for the Law Creation API endpoint."""

    def setUp(self):
        # Create user
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass123"
        )

        # Create permission and permission group for write access
        self.write_permission, _ = APITokenPermission.objects.get_or_create(
            resource="laws", action="write"
        )
        self.permission_group = APITokenPermissionGroup.objects.create(
            name="laws_write_group"
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

        # Create a law book for testing
        self.lawbook = LawBook.objects.create(
            code="APILAW",
            title="API Law Book",
            slug="apilaw",
            revision_date=date(2021, 1, 1),
            latest=True,
        )

    def test_create_law_success(self):
        """Test successful law creation via API."""
        data = {
            "book_code": "APILAW",
            "section": "§ 1",
            "title": "API Created Law",
            "content": "<p>API law content</p>",
        }

        response = self.client.post("/api/laws/", data, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn("id", response.data)
        self.assertIn("slug", response.data)
        self.assertIn("book_id", response.data)
        self.assertEqual(response.data["book_id"], self.lawbook.id)

    def test_create_law_book_not_found_returns_400(self):
        """Test law creation with non-existent book returns 400."""
        data = {
            "book_code": "NONEXISTENT",
            "section": "§ 1",
            "title": "Test Law",
            "content": "<p>Test content</p>",
        }

        response = self.client.post("/api/laws/", data, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_law_duplicate_returns_409(self):
        """Test duplicate law returns 409 Conflict."""
        # Create first law
        Law.objects.create(
            book=self.lawbook,
            section="§ 999",
            title="Original Law",
            content="<p>Original</p>",
            slug="999",
        )

        data = {
            "book_code": "APILAW",
            "section": "§ 999",  # Same section, same slug
            "title": "Duplicate Law",
            "content": "<p>Duplicate</p>",
        }

        response = self.client.post("/api/laws/", data, format="json")

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)

    def test_create_law_without_authentication_returns_401(self):
        """Test unauthenticated request returns 401."""
        self.client.force_authenticate(user=None, token=None)

        data = {
            "book_code": "APILAW",
            "section": "§ 1",
            "title": "No Auth Law",
            "content": "<p>No auth content</p>",
        }

        response = self.client.post("/api/laws/", data, format="json")

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_create_law_tracks_api_token(self):
        """Test that API token is tracked on created law."""
        data = {
            "book_code": "APILAW",
            "section": "§ 500",
            "title": "Token Law",
            "content": "<p>Token content</p>",
        }

        response = self.client.post("/api/laws/", data, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        # Verify token was tracked
        law = Law.objects.get(pk=response.data["id"])
        self.assertEqual(law.created_by_token, self.token)

    def test_create_law_missing_required_fields_returns_400(self):
        """Test missing required fields returns 400."""
        data = {
            "book_code": "APILAW",
            # Missing section, title, content
        }

        response = self.client.post("/api/laws/", data, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("section", response.data)
        self.assertIn("title", response.data)
        self.assertIn("content", response.data)


class LawBookRevisionIntegrationTestCase(APITestCase):
    """
    Full integration tests for law book revision management.
    """

    def setUp(self):
        self.user = User.objects.create_user(
            username="revisionuser", email="revision@example.com", password="testpass"
        )

        write_permission, _ = APITokenPermission.objects.get_or_create(
            resource="lawbooks", action="write"
        )
        permission_group = APITokenPermissionGroup.objects.create(
            name="revision_write_group"
        )
        permission_group.permissions.add(write_permission)

        self.token = APIToken.objects.create(
            user=self.user, name="Revision Token", permission_group=permission_group
        )

        self.client = APIClient()
        self.client.force_authenticate(user=self.user, token=self.token)

    def test_revision_management_flow(self):
        """Test complete revision management flow."""
        # Create initial revision (2020)
        response1 = self.client.post("/api/law_books/", {
            "code": "REVTEST",
            "title": "Revision Test Book 2020",
            "revision_date": "2020-01-01",
        }, format="json")
        self.assertEqual(response1.status_code, status.HTTP_201_CREATED)
        self.assertTrue(response1.data["latest"])
        book_2020_id = response1.data["id"]

        # Create newer revision (2021) - should become latest
        response2 = self.client.post("/api/law_books/", {
            "code": "REVTEST",
            "title": "Revision Test Book 2021",
            "revision_date": "2021-01-01",
        }, format="json")
        self.assertEqual(response2.status_code, status.HTTP_201_CREATED)
        self.assertTrue(response2.data["latest"])

        # Verify 2020 revision is no longer latest
        book_2020 = LawBook.objects.get(pk=book_2020_id)
        self.assertFalse(book_2020.latest)

        # Create older revision (2019) - should NOT become latest
        response3 = self.client.post("/api/law_books/", {
            "code": "REVTEST",
            "title": "Revision Test Book 2019",
            "revision_date": "2019-01-01",
        }, format="json")
        self.assertEqual(response3.status_code, status.HTTP_201_CREATED)
        self.assertFalse(response3.data["latest"])

        # Verify counts
        self.assertEqual(
            LawBook.objects.filter(code="REVTEST").count(),
            3
        )
        self.assertEqual(
            LawBook.objects.filter(code="REVTEST", latest=True).count(),
            1
        )
