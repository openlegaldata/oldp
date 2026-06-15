"""Verify /api/cases/<id>/citing_laws/ omits the law `content` field.

`Law.content` can be megabytes of HTML. The citing-laws action returns a
paginated list of *related* laws, so it should use the lean
``LawListSerializer`` (content omitted) exactly like its sibling
``/api/laws/<id>/citing_laws/`` does.

This also matters for DB load: ``citing_laws_for_case`` defers
``content`` via ``Law.defer_fields_list_view``. Serialising that queryset
with the full ``LawSerializer`` accesses ``.content`` per row, which both
re-fetches the deferred field (an extra query per law) and inflates the
response payload. Using the list serializer keeps the defer effective.
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
from oldp.apps.cases.models import Case
from oldp.apps.laws.models import Law, LawBook
from oldp.apps.references.models import LawReferenceMarker, Reference

User = get_user_model()


@override_settings(
    CACHES={"default": {"BACKEND": "django.core.cache.backends.dummy.DummyCache"}}
)
class CaseCitingLawsOmitsContentAPITestCase(APITestCase):
    fixtures = [
        "locations/countries.json",
        "locations/states.json",
        "locations/cities.json",
        "courts/courts.json",
    ]

    def setUp(self):
        self.user = User.objects.create_user(
            username="reader", email="reader@example.com", password="pass"
        )
        read_perm, _ = APITokenPermission.objects.get_or_create(
            resource="cases", action="read"
        )
        group = APITokenPermissionGroup.objects.create(name="cases_read")
        group.permissions.add(read_perm)
        self.token = APIToken.objects.create(
            user=self.user, name="reader-token", permission_group=group
        )

        # Cited case (the one whose citing_laws we query).
        self.case = Case.objects.create(
            file_number="CITED-CASE/01",
            date=datetime.date(2021, 1, 1),
            content="<p>Cited case body</p>",
            review_status="accepted",
        )

        # A law with a large content body that cites the case above.
        self.book = LawBook.objects.create(
            code="BGB",
            title="Bürgerliches Gesetzbuch",
            slug="bgb",
            revision_date=datetime.date(2021, 1, 1),
            review_status="accepted",
            latest=True,
        )
        self.content_html = "<p>Statutory text " + ("x" * 5_000) + "</p>"
        self.citing_law = Law.objects.create(
            book=self.book,
            title="§ 1 BGB",
            slug="1",
            section="1",
            order=1,
            content=self.content_html,
            review_status="accepted",
        )

        # Wire up the citation: a LawReferenceMarker on the citing law,
        # linked to a Reference that targets the cited case.
        reference = Reference.objects.create(
            case=self.case, to="case/%i" % self.case.pk
        )
        marker = LawReferenceMarker.objects.create(
            referenced_by=self.citing_law,
            text="BGH, Urteil",
            start=0,
            end=10,
        )
        marker.references.add(reference)

        self.client = APIClient()
        self.client.force_authenticate(user=self.user, token=self.token)

    def test_citing_laws_action_omits_content(self):
        response = self.client.get(f"/api/cases/{self.case.pk}/citing_laws/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data.get("results", response.data)
        # The citing law must be present...
        self.assertGreaterEqual(len(results), 1)
        ids = {item["id"] for item in results}
        self.assertIn(self.citing_law.pk, ids)
        # ...but its multi-MB content field must be omitted.
        for item in results:
            self.assertNotIn("content", item)
            self.assertIn("id", item)
            self.assertIn("title", item)
            self.assertIn("slug", item)
