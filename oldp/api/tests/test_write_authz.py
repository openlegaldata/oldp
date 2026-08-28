"""End-to-end authorization tests for content write endpoints.

Regression tests for the API write-authz hardening (internal-tools #14 & #15):

* #14 — a website **session**-authenticated user (no API token) must not be able
  to perform token-gated writes; ``HasTokenPermission`` previously allowed any
  non-token authenticated request.
* #15 — mutating a law / law book / court (including flipping ``review_status``
  to publish) is a moderation action and must be **staff-only**, mirroring the
  guard already present on ``CaseViewSet``.
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
from oldp.apps.laws.models import Law, LawBook

User = get_user_model()


@override_settings(
    CACHES={"default": {"BACKEND": "django.core.cache.backends.dummy.DummyCache"}}
)
class ContentWriteAuthzTestCase(APITestCase):
    """Session users must not bypass token-gated / staff-only content writes."""

    def setUp(self):
        self.user = User.objects.create_user("writer", "w@example.com", "pass")
        self.staff = User.objects.create_user(
            "moderator", "mod@example.com", "pass", is_staff=True
        )
        self.book = LawBook.objects.create(
            code="test",
            title="Test Book",
            slug="test-book",
            revision_date=date(2020, 1, 1),
            review_status="accepted",
            latest=True,
        )
        self.law = Law.objects.create(
            book=self.book,
            title="§ 1 Test",
            slug="test-1",
            section="1",
            content="<p>original</p>",
            review_status="accepted",
            order=0,
        )

    # --- #14: session auth (no token) must not perform token-gated writes ---

    def test_session_user_cannot_patch_law(self):
        client = APIClient()
        client.force_authenticate(user=self.user)  # no token -> request.auth is None
        res = client.patch(f"/api/laws/{self.law.id}/", {"review_status": "pending"})
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)
        self.law.refresh_from_db()
        self.assertEqual(self.law.review_status, "accepted")  # unchanged

    def test_session_user_cannot_patch_law_book(self):
        client = APIClient()
        client.force_authenticate(user=self.user)
        res = client.patch(
            f"/api/law_books/{self.book.id}/", {"review_status": "pending"}
        )
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_session_user_cannot_delete_law(self):
        client = APIClient()
        client.force_authenticate(user=self.user)
        res = client.delete(f"/api/laws/{self.law.id}/")
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)
        self.assertTrue(Law.objects.filter(id=self.law.id).exists())

    def test_session_user_can_still_read_law(self):
        client = APIClient()
        client.force_authenticate(user=self.user)
        res = client.get(f"/api/laws/{self.law.id}/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)

    # --- #15: even a write-scoped token may not mutate/publish (staff-only) ---

    def test_write_token_cannot_patch_law(self):
        write_perm, _ = APITokenPermission.objects.get_or_create(
            resource="laws", action="write"
        )
        group = APITokenPermissionGroup.objects.create(name="laws_write_test")
        group.permissions.add(write_perm)
        token = APIToken.objects.create(
            user=self.user, name="write-token", permission_group=group
        )
        client = APIClient()
        client.force_authenticate(user=self.user, token=token)
        res = client.patch(f"/api/laws/{self.law.id}/", {"review_status": "pending"})
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)
        self.law.refresh_from_db()
        self.assertEqual(self.law.review_status, "accepted")  # not flipped

    # --- #15: staff may moderate ---

    def test_staff_user_can_patch_law_review_status(self):
        client = APIClient()
        client.force_authenticate(user=self.staff)
        res = client.patch(f"/api/laws/{self.law.id}/", {"review_status": "pending"})
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.law.refresh_from_db()
        self.assertEqual(self.law.review_status, "pending")
