"""Tests for review_status-based filtering and visibility in the Law and LawBook APIs."""

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
class LawBookReviewStatusAPITestCase(APITestCase):
    """Tests for review_status filtering and field visibility on the LawBook API."""

    def setUp(self):
        # Users and tokens
        self.user_a = User.objects.create_user(
            username="user_a", email="a@example.com", password="pass"
        )
        read_perm, _ = APITokenPermission.objects.get_or_create(
            resource="lawbooks", action="read"
        )
        group = APITokenPermissionGroup.objects.create(name="lawbooks_read")
        group.permissions.add(read_perm)
        self.token_a = APIToken.objects.create(
            user=self.user_a, name="Token A", permission_group=group
        )

        self.user_b = User.objects.create_user(
            username="user_b", email="b@example.com", password="pass"
        )
        self.token_b = APIToken.objects.create(
            user=self.user_b, name="Token B", permission_group=group
        )

        self.staff_user = User.objects.create_user(
            username="staff", email="staff@example.com", password="pass", is_staff=True
        )
        self.token_staff = APIToken.objects.create(
            user=self.staff_user, name="Token Staff", permission_group=group
        )

        # LawBooks with different review statuses
        self.accepted_book = LawBook.objects.create(
            code="BGB",
            title="Bürgerliches Gesetzbuch",
            slug="bgb",
            revision_date=datetime.date(2021, 1, 1),
            review_status="accepted",
        )
        self.pending_book_a = LawBook.objects.create(
            code="TESTBOOK",
            title="Test Book",
            slug="testbook",
            revision_date=datetime.date(2021, 2, 1),
            review_status="pending",
            created_by_token=self.token_a,
        )
        self.pending_book_b = LawBook.objects.create(
            code="OTHERBOOK",
            title="Other Book",
            slug="otherbook",
            revision_date=datetime.date(2021, 3, 1),
            review_status="pending",
            created_by_token=self.token_b,
        )

        self.client = APIClient()

    def _get_ids(self, response):
        return {item["id"] for item in response.data["results"]}

    def test_list_returns_only_accepted_for_regular_user(self):
        """Regular user sees accepted + own pending lawbooks."""
        self.client.force_authenticate(user=self.user_a, token=self.token_a)
        response = self.client.get("/api/law_books/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = self._get_ids(response)
        self.assertIn(self.accepted_book.pk, ids)
        self.assertIn(self.pending_book_a.pk, ids)
        self.assertNotIn(self.pending_book_b.pk, ids)

    def test_list_staff_sees_all(self):
        """Staff user sees all lawbooks."""
        self.client.force_authenticate(user=self.staff_user, token=self.token_staff)
        response = self.client.get("/api/law_books/")

        ids = self._get_ids(response)
        self.assertIn(self.accepted_book.pk, ids)
        self.assertIn(self.pending_book_a.pk, ids)
        self.assertIn(self.pending_book_b.pk, ids)

    def test_detail_returns_404_for_others_pending(self):
        """Non-owner cannot access another user's pending lawbook."""
        self.client.force_authenticate(user=self.user_b, token=self.token_b)
        response = self.client.get(f"/api/law_books/{self.pending_book_a.pk}/")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_detail_owner_can_access_pending(self):
        """Owner can access their own pending lawbook."""
        self.client.force_authenticate(user=self.user_a, token=self.token_a)
        response = self.client.get(f"/api/law_books/{self.pending_book_a.pk}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_review_status_hidden_for_non_owner(self):
        """review_status is hidden for non-owner users."""
        self.client.force_authenticate(user=self.user_b, token=self.token_b)
        response = self.client.get(f"/api/law_books/{self.accepted_book.pk}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertNotIn("review_status", response.data)

    def test_review_status_visible_for_owner(self):
        """Owner sees review_status on their own lawbook."""
        self.client.force_authenticate(user=self.user_a, token=self.token_a)
        response = self.client.get(f"/api/law_books/{self.pending_book_a.pk}/")
        self.assertIn("review_status", response.data)
        self.assertEqual(response.data["review_status"], "pending")

    def test_review_status_visible_for_staff(self):
        """Staff sees review_status on all lawbooks."""
        self.client.force_authenticate(user=self.staff_user, token=self.token_staff)
        response = self.client.get(f"/api/law_books/{self.accepted_book.pk}/")
        self.assertIn("review_status", response.data)

    def test_list_response_has_cache_vary_headers(self):
        """Cached API responses vary by auth/session and locale/domain headers."""
        self.client.force_authenticate(user=self.user_a, token=self.token_a)
        response = self.client.get(
            "/api/law_books/",
            HTTP_ACCEPT_LANGUAGE="de",
            HTTP_HOST="testserver",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        vary = response.get("Vary", "")
        self.assertIn("Authorization", vary)
        self.assertIn("Cookie", vary)
        self.assertIn("Accept-Language", vary)
        self.assertIn("Host", vary)


@override_settings(
    CACHES={"default": {"BACKEND": "django.core.cache.backends.dummy.DummyCache"}}
)
class LawReviewStatusAPITestCase(APITestCase):
    """Tests for review_status filtering and field visibility on the Law API."""

    def setUp(self):
        # Users and tokens
        self.user_a = User.objects.create_user(
            username="law_user_a", email="law_a@example.com", password="pass"
        )
        read_perm, _ = APITokenPermission.objects.get_or_create(
            resource="laws", action="read"
        )
        group = APITokenPermissionGroup.objects.create(name="laws_read")
        group.permissions.add(read_perm)
        self.token_a = APIToken.objects.create(
            user=self.user_a, name="Token A", permission_group=group
        )

        self.user_b = User.objects.create_user(
            username="law_user_b", email="law_b@example.com", password="pass"
        )
        self.token_b = APIToken.objects.create(
            user=self.user_b, name="Token B", permission_group=group
        )

        self.staff_user = User.objects.create_user(
            username="law_staff",
            email="law_staff@example.com",
            password="pass",
            is_staff=True,
        )
        self.token_staff = APIToken.objects.create(
            user=self.staff_user, name="Token Staff", permission_group=group
        )

        # Create a lawbook for the laws
        self.book = LawBook.objects.create(
            code="TSTBK",
            title="Test Book",
            slug="tstbk",
            revision_date=datetime.date(2021, 1, 1),
            review_status="accepted",
        )

        # Laws with different review statuses
        self.accepted_law = Law.objects.create(
            book=self.book,
            title="Accepted Law",
            slug="par-1",
            section="§ 1",
            content="<p>Accepted</p>",
            review_status="accepted",
        )
        self.pending_law_a = Law.objects.create(
            book=self.book,
            title="Pending Law A",
            slug="par-2",
            section="§ 2",
            content="<p>Pending A</p>",
            review_status="pending",
            created_by_token=self.token_a,
        )
        self.pending_law_b = Law.objects.create(
            book=self.book,
            title="Pending Law B",
            slug="par-3",
            section="§ 3",
            content="<p>Pending B</p>",
            review_status="pending",
            created_by_token=self.token_b,
        )

        self.client = APIClient()

    def _get_ids(self, response):
        return {item["id"] for item in response.data["results"]}

    def test_list_returns_only_accepted_and_own_for_regular_user(self):
        """Regular user sees accepted + own pending laws."""
        self.client.force_authenticate(user=self.user_a, token=self.token_a)
        response = self.client.get("/api/laws/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = self._get_ids(response)
        self.assertIn(self.accepted_law.pk, ids)
        self.assertIn(self.pending_law_a.pk, ids)
        self.assertNotIn(self.pending_law_b.pk, ids)

    def test_list_staff_sees_all(self):
        """Staff user sees all laws."""
        self.client.force_authenticate(user=self.staff_user, token=self.token_staff)
        response = self.client.get("/api/laws/")

        ids = self._get_ids(response)
        self.assertIn(self.accepted_law.pk, ids)
        self.assertIn(self.pending_law_a.pk, ids)
        self.assertIn(self.pending_law_b.pk, ids)

    def test_detail_returns_404_for_others_pending(self):
        """Non-owner cannot access another user's pending law."""
        self.client.force_authenticate(user=self.user_b, token=self.token_b)
        response = self.client.get(f"/api/laws/{self.pending_law_a.pk}/")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_detail_owner_can_access_pending(self):
        """Owner can access their own pending law."""
        self.client.force_authenticate(user=self.user_a, token=self.token_a)
        response = self.client.get(f"/api/laws/{self.pending_law_a.pk}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_review_status_hidden_for_non_owner(self):
        """review_status is hidden for non-owner users."""
        self.client.force_authenticate(user=self.user_b, token=self.token_b)
        response = self.client.get(f"/api/laws/{self.accepted_law.pk}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertNotIn("review_status", response.data)

    def test_review_status_visible_for_owner(self):
        """Owner sees review_status on their own law."""
        self.client.force_authenticate(user=self.user_a, token=self.token_a)
        response = self.client.get(f"/api/laws/{self.pending_law_a.pk}/")
        self.assertIn("review_status", response.data)
        self.assertEqual(response.data["review_status"], "pending")

    def test_review_status_visible_for_staff(self):
        """Staff sees review_status on all laws."""
        self.client.force_authenticate(user=self.staff_user, token=self.token_staff)
        response = self.client.get(f"/api/laws/{self.accepted_law.pk}/")
        self.assertIn("review_status", response.data)
