"""Unit tests for the Law and LawBook Creation API.

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

    def _make_api_token(self):
        """A minimal APIToken so create_lawbook takes the pending submission path."""
        user = User.objects.create_user(username="ingestor", password="x")
        return APIToken.objects.create(user=user, name="Ingestor Token")

    def test_pending_revision_does_not_demote_published_latest(self):
        """A pending (API) submission must NOT demote the published revision.

        Root-cause regression for the "Grundgesetz has no latest revision"
        bug: ingesting a newer revision via the API used to flip the live,
        accepted revision to ``latest=False`` immediately while the new
        revision sat ``pending`` — leaving the book with no publicly-visible
        latest. The latest flag must stay on the published revision until the
        new one is approved.
        """
        published = self.creator.create_lawbook(
            code="GGTEST", title="GG 2010", revision_date=date(2010, 1, 1)
        )
        self.assertTrue(published.latest)

        pending = self.creator.create_lawbook(
            code="GGTEST",
            title="GG 2020",
            revision_date=date(2020, 1, 1),
            api_token=self._make_api_token(),
        )
        published.refresh_from_db()

        self.assertEqual(pending.review_status, "pending")
        self.assertFalse(pending.latest)  # not yet the published latest
        self.assertTrue(published.latest)  # still the published latest
        self.assertEqual(LawBook.objects.filter(code="GGTEST", latest=True).count(), 1)

    def test_approving_pending_revision_promotes_it(self):
        """Approving a newer pending revision promotes it and demotes the old."""
        published = self.creator.create_lawbook(
            code="GGTEST", title="GG 2010", revision_date=date(2010, 1, 1)
        )
        pending = self.creator.create_lawbook(
            code="GGTEST",
            title="GG 2020",
            revision_date=date(2020, 1, 1),
            api_token=self._make_api_token(),
        )

        # Approve — what the admin / API approval path does.
        pending.review_status = "accepted"
        pending.save()
        LawBook.refresh_latest_for_code("GGTEST")

        published.refresh_from_db()
        pending.refresh_from_db()
        self.assertTrue(pending.latest)
        self.assertFalse(published.latest)
        self.assertEqual(LawBook.objects.filter(code="GGTEST", latest=True).count(), 1)

    def test_rejecting_pending_revision_keeps_published_latest(self):
        """Rejecting a pending revision leaves the published latest intact."""
        published = self.creator.create_lawbook(
            code="GGTEST", title="GG 2010", revision_date=date(2010, 1, 1)
        )
        pending = self.creator.create_lawbook(
            code="GGTEST",
            title="GG 2020",
            revision_date=date(2020, 1, 1),
            api_token=self._make_api_token(),
        )

        pending.review_status = "rejected"
        pending.save()
        LawBook.refresh_latest_for_code("GGTEST")

        published.refresh_from_db()
        self.assertTrue(published.latest)
        self.assertFalse(LawBook.objects.get(pk=pending.pk).latest)

    def test_refresh_latest_for_code_clears_when_no_accepted(self):
        """A code with no accepted revision ends up with no latest flag."""
        self.creator.create_lawbook(
            code="ONLYPENDING",
            title="Only Pending",
            revision_date=date(2020, 1, 1),
            api_token=self._make_api_token(),
        )
        # Force a stale flag, then refresh.
        LawBook.objects.filter(code="ONLYPENDING").update(latest=True)
        result = LawBook.refresh_latest_for_code("ONLYPENDING")

        self.assertIsNone(result)
        self.assertEqual(
            LawBook.objects.filter(code="ONLYPENDING", latest=True).count(), 0
        )

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
        # Submitted via an API token => pending review, so it is not yet the
        # published latest revision. The latest flag flips only on approval.
        self.assertEqual(response.data["review_status"], "pending")
        self.assertFalse(response.data["latest"])

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

    def test_create_law_db_data_error_returns_400_not_500(self):
        """A DB-side encoding rejection should surface as 400, not 500.

        Reproduces the production failure where ``POST /api/laws/`` for
        Brüssel-Ia-VO Art. 3 raised an opaque HTTP 500 because the
        MariaDB ``laws_law.content`` column charset (latin1/utf8mb3
        pre-migration) could not store Hungarian/Swedish glyphs and
        typographic quotes appearing in the German EUR-Lex body. The
        underlying schema fix lives in migration
        ``0025_convert_utf8mb4``; this test guards the API-layer
        translation so any future column-level oversight does not
        regress to a 500 again.
        """
        from unittest.mock import patch

        from django.db import DataError

        # Content shape mirrors the Brüssel-Ia-VO Art. 3 payload that
        # tripped prod: extended Latin (ő) plus directional quotes
        # („ “) inside HTML tables.
        content = (
            "<div><p>Für die Zwecke dieser Verordnung umfasst der Begriff "
            "„Gericht“ die folgenden Behörden: in Ungarn, bei "
            "summarischen Mahnverfahren (fizetési meghagyásos eljárás), "
            "den Notar (közjegyző).</p></div>"
        )
        data = {
            "book_code": "APILAW",
            "section": "Art. 3 mb4 regression",
            "title": "Artikel 3",
            "content": content,
        }
        # SQLite happily stores anything regardless of declared charset,
        # so simulate the MariaDB-side rejection by raising DataError
        # from the creator. The view must translate to 400.
        with patch(
            "oldp.apps.laws.api_views.LawCreator.create_law",
            side_effect=DataError(1366, 'Incorrect string value: "..." '),
        ):
            response = self.client.post("/api/laws/", data, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("detail", response.data)
        self.assertIn("charset", str(response.data["detail"]))


class LawBookRevisionIntegrationTestCase(APITestCase):
    """Full integration tests for law book revision management."""

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

    def _post_revision(self, year):
        return self.client.post(
            "/api/law_books/",
            {
                "code": "REVTEST",
                "title": f"Revision Test Book {year}",
                "revision_date": f"{year}-01-01",
            },
            format="json",
        )

    def _approve(self, pk):
        """Simulate approval (what the admin / API approval path does)."""
        LawBook.objects.filter(pk=pk).update(review_status="accepted")
        LawBook.refresh_latest_for_code("REVTEST")

    def test_revision_management_flow(self):
        """Pending submissions don't claim latest; approval drives the flag.

        Revisions submitted via the API are created ``pending`` and must not
        take (or steal) the published ``latest`` flag. The newest *accepted*
        revision is the latest, established when a revision is approved.
        """
        # Submit two revisions — both pending, neither is latest.
        r2020 = self._post_revision(2020)
        r2021 = self._post_revision(2021)
        self.assertEqual(r2020.status_code, status.HTTP_201_CREATED)
        self.assertEqual(r2021.status_code, status.HTTP_201_CREATED)
        self.assertFalse(r2020.data["latest"])
        self.assertFalse(r2021.data["latest"])
        # No accepted revision yet => no published latest.
        self.assertEqual(LawBook.objects.filter(code="REVTEST", latest=True).count(), 0)

        # Approve 2020 — it becomes the published latest.
        self._approve(r2020.data["id"])
        self.assertTrue(LawBook.objects.get(pk=r2020.data["id"]).latest)
        self.assertEqual(LawBook.objects.filter(code="REVTEST", latest=True).count(), 1)

        # Approve the newer 2021 — it takes over, 2020 is demoted.
        self._approve(r2021.data["id"])
        self.assertTrue(LawBook.objects.get(pk=r2021.data["id"]).latest)
        self.assertFalse(LawBook.objects.get(pk=r2020.data["id"]).latest)

        # Submit + approve an older 2019 — must NOT become latest.
        r2019 = self._post_revision(2019)
        self._approve(r2019.data["id"])
        self.assertFalse(LawBook.objects.get(pk=r2019.data["id"]).latest)
        self.assertTrue(LawBook.objects.get(pk=r2021.data["id"]).latest)

        # Verify counts.
        self.assertEqual(LawBook.objects.filter(code="REVTEST").count(), 3)
        self.assertEqual(LawBook.objects.filter(code="REVTEST", latest=True).count(), 1)
