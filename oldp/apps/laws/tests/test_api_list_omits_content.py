"""Verify /api/laws/ list responses omit the `content` field.

Law content can be megabytes of HTML; returning it in the list view
makes bulk pagination expensive on origin CPU and bandwidth. The
detail view (`/api/laws/<id>/`) continues to return content. Mirrors
the existing Case list/detail split.
"""

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
class LawListOmitsContentAPITestCase(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="reader", email="reader@example.com", password="pass"
        )
        read_perm, _ = APITokenPermission.objects.get_or_create(
            resource="laws", action="read"
        )
        group = APITokenPermissionGroup.objects.create(name="laws_read")
        group.permissions.add(read_perm)
        self.token = APIToken.objects.create(
            user=self.user, name="reader-token", permission_group=group
        )

        self.book = LawBook.objects.create(
            code="BGB",
            title="Bürgerliches Gesetzbuch",
            slug="bgb",
            revision_date=datetime.date(2021, 1, 1),
            review_status="accepted",
            latest=True,
        )
        self.content_html = "<p>Some statutory text " + ("x" * 5_000) + "</p>"
        self.law = Law.objects.create(
            book=self.book,
            title="§ 1 BGB",
            slug="1",
            section="1",
            order=1,
            content=self.content_html,
            review_status="accepted",
        )

        self.client = APIClient()
        self.client.force_authenticate(user=self.user, token=self.token)

    def test_list_response_omits_content(self):
        response = self.client.get("/api/laws/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(len(response.data["results"]), 1)
        for item in response.data["results"]:
            self.assertNotIn("content", item)
            # Other expected fields stay present
            self.assertIn("id", item)
            self.assertIn("title", item)
            self.assertIn("slug", item)

    def test_detail_response_includes_content(self):
        response = self.client.get(f"/api/laws/{self.law.pk}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("content", response.data)
        self.assertEqual(response.data["content"], self.content_html)

    def test_citing_laws_action_omits_content(self):
        # citing_laws returns a paginated list of related laws; same
        # rationale as the main list view — should omit `content`.
        response = self.client.get(f"/api/laws/{self.law.pk}/citing_laws/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data.get("results", response.data)
        for item in results:
            self.assertNotIn("content", item)
