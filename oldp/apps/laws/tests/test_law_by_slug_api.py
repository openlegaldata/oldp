"""Tests for the GET /api/laws/by_slug/{book_slug}/{law_slug}/ endpoint."""

import datetime

from django.contrib.auth import get_user_model
from django.test import override_settings
from rest_framework import status
from rest_framework.test import APIClient, APITestCase

from oldp.apps.accounts.models import (
    APIToken,
    APITokenPermission,
    APITokenPermissionGroup,
)
from oldp.apps.laws.models import Law, LawBook

User = get_user_model()


@override_settings(
    CACHES={"default": {"BACKEND": "django.core.cache.backends.dummy.DummyCache"}}
)
class LawBySlugAPITestCase(APITestCase):
    """Tests for the by_slug action on LawViewSet."""

    def setUp(self):
        read_perm, _ = APITokenPermission.objects.get_or_create(
            resource="laws", action="read"
        )
        group = APITokenPermissionGroup.objects.create(name="laws_read_by_slug")
        group.permissions.add(read_perm)

        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="pass"
        )
        self.token = APIToken.objects.create(
            user=self.user, name="Test Token", permission_group=group
        )

        self.book = LawBook.objects.create(
            code="BGB",
            title="Bürgerliches Gesetzbuch",
            slug="bgb",
            revision_date=datetime.date(2021, 1, 1),
            review_status="accepted",
        )
        self.law = Law.objects.create(
            book=self.book,
            slug="1",
            section="§ 1",
            title="Rechtsfähigkeit",
            content="<p>Die Rechtsfähigkeit des Menschen beginnt...</p>",
            review_status="accepted",
        )

        self.client = APIClient()
        self.client.force_authenticate(user=self.user, token=self.token)

    def test_by_slug_returns_law(self):
        """Returns the law for a valid book_slug and law_slug."""
        response = self.client.get(f"/api/laws/by_slug/{self.book.slug}/{self.law.slug}/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["slug"], self.law.slug)
        self.assertEqual(response.data["title"], self.law.title)

    def test_by_slug_wrong_law_slug_returns_404(self):
        """Returns 404 when the law slug does not exist in the given book."""
        response = self.client.get(f"/api/laws/by_slug/{self.book.slug}/nonexistent/")

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_by_slug_wrong_book_slug_returns_404(self):
        """Returns 404 when the book slug does not exist."""
        response = self.client.get(f"/api/laws/by_slug/nonexistent/{self.law.slug}/")

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_by_slug_law_in_different_book_returns_404(self):
        """Returns 404 when the law exists but belongs to a different book."""
        other_book = LawBook.objects.create(
            code="STGB",
            title="Strafgesetzbuch",
            slug="stgb",
            revision_date=datetime.date(2021, 1, 1),
            review_status="accepted",
        )
        response = self.client.get(f"/api/laws/by_slug/{other_book.slug}/{self.law.slug}/")

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_by_slug_returns_latest_revision_when_multiple_exist(self):
        """Returns the law from the latest revision when a book has multiple revisions."""
        old_book = LawBook.objects.create(
            code="BGB",
            title="Bürgerliches Gesetzbuch (alt)",
            slug="bgb",
            revision_date=datetime.date(2020, 1, 1),
            latest=False,
            review_status="accepted",
        )
        Law.objects.create(
            book=old_book,
            slug="par-1",
            section="§ 1",
            title="Alte Fassung",
            content="<p>Alt.</p>",
            review_status="accepted",
        )

        response = self.client.get(f"/api/laws/by_slug/{self.book.slug}/{self.law.slug}/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["title"], self.law.title)
