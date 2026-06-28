"""Tests for DSGVO/GDPR self-service: data export (ZIP) + account deletion."""

import io
import json
import zipfile
from datetime import date

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from oldp.apps.accounts import gdpr
from oldp.apps.accounts.models import APIToken

PASSWORD = "testpass123"


class DataExportTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("expuser", "exp@example.com", PASSWORD)
        self.user.profile.organization = "ACME"
        self.user.profile.role = self.user.profile.ROLE_DEVELOPER
        self.user.profile.save()
        APIToken.objects.create(user=self.user, name="prod", rate_limit=20000)
        self.client.force_login(self.user)

    def test_export_returns_zip(self):
        res = self.client.get(reverse("account_data_export"))
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res["Content-Type"], "application/zip")
        self.assertIn("attachment", res["Content-Disposition"])
        self.assertIn("expuser", res["Content-Disposition"])

    def test_zip_contents(self):
        res = self.client.get(reverse("account_data_export"))
        zf = zipfile.ZipFile(io.BytesIO(res.content))
        names = zf.namelist()
        self.assertIn("README.txt", names)
        self.assertIn("account.json", names)

        data = json.loads(zf.read("account.json"))
        self.assertEqual(data["account"]["username"], "expuser")
        self.assertEqual(data["account"]["email"], "exp@example.com")
        self.assertEqual(data["profile"]["organization"], "ACME")
        self.assertEqual(len(data["api_tokens"]), 1)
        self.assertEqual(data["api_tokens"][0]["name"], "prod")
        self.assertEqual(data["api_tokens"][0]["rate_limit"], 20000)

    def test_token_secret_is_masked(self):
        token = APIToken.objects.filter(user=self.user).first()
        res = self.client.get(reverse("account_data_export"))
        body = res.content
        self.assertNotIn(token.key.encode(), body)

    def test_readme_is_bilingual(self):
        res = self.client.get(reverse("account_data_export"))
        zf = zipfile.ZipFile(io.BytesIO(res.content))
        readme = zf.read("README.txt").decode()
        self.assertIn("Datenexport", readme)
        self.assertIn("data export", readme)

    def test_export_requires_login(self):
        self.client.logout()
        res = self.client.get(reverse("account_data_export"))
        self.assertEqual(res.status_code, 302)


class AccountDeleteTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("deluser", "del@example.com", PASSWORD)
        self.client.force_login(self.user)

    def test_get_renders_confirmation(self):
        res = self.client.get(reverse("account_delete"))
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "deluser")

    def test_wrong_username_does_not_delete(self):
        res = self.client.post(reverse("account_delete"), {"confirm_username": "wrong"})
        self.assertEqual(res.status_code, 200)
        self.assertTrue(User.objects.filter(username="deluser").exists())

    def test_correct_username_deletes_and_logs_out(self):
        res = self.client.post(
            reverse("account_delete"), {"confirm_username": "deluser"}, follow=True
        )
        self.assertFalse(User.objects.filter(username="deluser").exists())
        # Session no longer authenticated.
        self.assertFalse(res.context["user"].is_authenticated)

    def test_delete_requires_login(self):
        self.client.logout()
        res = self.client.get(reverse("account_delete"))
        self.assertEqual(res.status_code, 302)


class DeletionKeepsContentTests(TestCase):
    def test_token_created_content_survives_user_deletion(self):
        from oldp.apps.cases.models import Case
        from oldp.apps.courts.models import Country, Court, State

        country = Country.objects.create(name="Testcountry", code="de")
        state = State.objects.create(name="Testland", slug="testland", country=country)
        court = Court.objects.create(
            name="Testgericht", code="TESTG", slug="testgericht", state=state
        )
        user = User.objects.create_user("owner", "owner@example.com", PASSWORD)
        token = APIToken.objects.create(user=user, name="t")
        case = Case.objects.create(
            court=court,
            file_number="GDPR-1",
            date=date(2020, 1, 1),
            content="<p>kept</p>",
            created_by_token=token,
        )

        gdpr.delete_user_account(user)

        case.refresh_from_db()
        self.assertTrue(Case.objects.filter(pk=case.pk).exists())
        # User + token gone, attribution nulled, content row kept.
        self.assertFalse(User.objects.filter(username="owner").exists())
        self.assertIsNone(case.created_by_token_id)
