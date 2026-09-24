"""Verify the case REST API never returns the case ``abstract``.

The abstract is accepted on case creation but is not part of the public
read output (neither detail nor list views); the MCP ``get_case`` tool
omits it as well.
"""

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

User = get_user_model()


@override_settings(
    CACHES={"default": {"BACKEND": "django.core.cache.backends.dummy.DummyCache"}}
)
class CaseAPIOmitsAbstractTestCase(APITestCase):
    fixtures = [
        "locations/countries.json",
        "locations/states.json",
        "locations/cities.json",
        "courts/courts.json",
    ]

    def setUp(self):
        user = User.objects.create_user(
            username="reader", email="reader@example.com", password="pass"
        )
        read_perm, _ = APITokenPermission.objects.get_or_create(
            resource="cases", action="read"
        )
        group = APITokenPermissionGroup.objects.create(name="cases_read")
        group.permissions.add(read_perm)
        token = APIToken.objects.create(
            user=user, name="reader-token", permission_group=group
        )
        self.case = Case.objects.create(
            file_number="ABSTRACT/01",
            court_id=1,
            content="<p>Inhalt</p>",
            abstract="<p>Leitsatz</p>",
            review_status="accepted",
        )
        self.client = APIClient()
        self.client.force_authenticate(user=user, token=token)

    def test_detail_omits_abstract(self):
        response = self.client.get(f"/api/cases/{self.case.pk}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("content", response.data)
        self.assertNotIn("abstract", response.data)

    def test_list_omits_abstract(self):
        response = self.client.get("/api/cases/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["results"])
        for item in response.data["results"]:
            self.assertNotIn("abstract", item)
