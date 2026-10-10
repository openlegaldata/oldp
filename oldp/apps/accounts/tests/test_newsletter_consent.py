"""Versioned, append-only newsletter consent text and the proof kept on the profile."""

import io
import json
import zipfile

from django.contrib.auth.models import User
from django.core import mail
from django.test import RequestFactory, TestCase
from django.urls import reverse
from django.utils import translation

from oldp.apps.accounts import lifecycle
from oldp.apps.accounts.forms import CustomSignupForm
from oldp.apps.accounts.models import NewsletterConsentText, UserProfile
from oldp.apps.accounts.newsletter import make_doi_token

PASSWORD = "testpass123"


class ConsentTextModelTests(TestCase):
    def test_seeded_by_migration(self):
        versions = set(NewsletterConsentText.objects.values_list("version", "language"))
        self.assertEqual(
            versions, {("2026-06", "en"), ("2026-10", "en"), ("2026-10", "de")}
        )

    def test_current_is_newest_per_language_with_english_fallback(self):
        self.assertEqual(NewsletterConsentText.current("de").version, "2026-10")
        self.assertEqual(NewsletterConsentText.current("de").language, "de")
        self.assertEqual(NewsletterConsentText.current("fr").language, "en")
        with translation.override("de"):
            self.assertEqual(NewsletterConsentText.current().language, "de")
        with translation.override("en-us"):
            self.assertEqual(NewsletterConsentText.current().language, "en")

    def test_newer_version_becomes_current(self):
        NewsletterConsentText.objects.create(
            version="2027-01", language="en", text="new"
        )
        self.assertEqual(NewsletterConsentText.current("en").text, "new")
        self.assertEqual(NewsletterConsentText.current("de").version, "2026-10")

    def test_append_only(self):
        row = NewsletterConsentText.current("en")
        row.text = "edited"
        with self.assertRaises(ValueError):
            row.save()
        with self.assertRaises(ValueError):
            row.delete()
        with self.assertRaises(ValueError):
            NewsletterConsentText.objects.get(pk=row.pk).delete()
        # Unchanged in the database.
        self.assertNotEqual(NewsletterConsentText.objects.get(pk=row.pk).text, "edited")

    def test_row_in_use_is_protected(self):
        from django.db.models import ProtectedError

        user = User.objects.create_user("p", "p@example.com", PASSWORD)
        user.profile.record_opt_in(UserProfile.CONSENT_SOURCE_DASHBOARD)
        user.profile.save()
        with self.assertRaises(ProtectedError):
            NewsletterConsentText.objects.filter(
                pk=user.profile.newsletter_consent_text_id
            ).delete()

    def test_admin_is_read_only(self):
        admin_user = User.objects.create_superuser("root", "root@example.com", "pw")
        self.client.force_login(admin_user)
        res = self.client.get(
            reverse("admin:accounts_newsletterconsenttext_changelist")
        )
        self.assertEqual(res.status_code, 200)
        res = self.client.get(reverse("admin:accounts_newsletterconsenttext_add"))
        self.assertIn(res.status_code, (401, 403))


class ConsentProofOnProfileTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("nl", "nl@example.com", PASSWORD)
        self.client.force_login(self.user)

    def test_opt_in_records_current_text(self):
        # The request language is chosen by domain (DomainLocaleMiddleware);
        # which language is picked is covered by the model tests above.
        self.client.post(
            reverse("account_newsletter_preference"), {"action": "subscribe"}
        )
        profile = self.user.profile
        profile.refresh_from_db()
        self.assertEqual(profile.newsletter_consent_text.version, "2026-10")
        self.assertIn(profile.newsletter_consent_text.language, ("en", "de"))
        # The confirmation mail quotes the same wording.
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn(profile.newsletter_consent_text.text, mail.outbox[0].body)

    def test_unsubscribe_keeps_proof_and_stamps_withdrawal(self):
        profile = self.user.profile
        profile.record_opt_in(UserProfile.CONSENT_SOURCE_DASHBOARD)
        profile.save()
        self.client.get(
            reverse(
                "account_newsletter_confirm",
                kwargs={"token": make_doi_token(self.user)},
            )
        )
        self.client.post(
            reverse("account_newsletter_preference"), {"action": "unsubscribe"}
        )
        profile.refresh_from_db()
        self.assertFalse(profile.newsletter_opt_in)
        self.assertFalse(profile.is_newsletter_subscriber)
        self.assertIsNotNone(profile.newsletter_opt_in_at)
        self.assertIsNotNone(profile.newsletter_doi_confirmed_at)
        self.assertIsNotNone(profile.newsletter_unsubscribed_at)
        self.assertEqual(profile.consent_source, UserProfile.CONSENT_SOURCE_DASHBOARD)
        self.assertIsNotNone(profile.newsletter_consent_text)

    def test_resubscribe_requires_new_confirmation(self):
        profile = self.user.profile
        profile.record_opt_in(UserProfile.CONSENT_SOURCE_DASHBOARD)
        profile.confirm_double_opt_in()
        profile.revoke_newsletter()
        profile.save()

        profile.record_opt_in(UserProfile.CONSENT_SOURCE_DASHBOARD)
        profile.save()
        self.assertTrue(profile.newsletter_opt_in)
        self.assertIsNone(profile.newsletter_doi_confirmed_at)
        self.assertIsNone(profile.newsletter_unsubscribed_at)
        self.assertFalse(profile.is_newsletter_subscriber)

    def test_signup_form_label_is_current_text_and_stored(self):
        with translation.override("de"):
            form = CustomSignupForm(
                data={
                    "organization": "",
                    "role": "",
                    "use_case": "",
                    "newsletter_opt_in": True,
                }
            )
            self.assertEqual(
                form.fields["newsletter_opt_in"].label,
                NewsletterConsentText.current("de").text,
            )
            self.assertTrue(form.is_valid(), form.errors)
            user = User.objects.create_user("su", "su@example.com", PASSWORD)
            form.signup(RequestFactory().get("/accounts/signup/"), user)
        user.profile.refresh_from_db()
        self.assertEqual(user.profile.newsletter_consent_text.language, "de")
        self.assertEqual(user.profile.consent_source, UserProfile.CONSENT_SOURCE_SIGNUP)

    def test_dashboard_shows_current_text(self):
        res = self.client.get(reverse("account_profile"))
        shown = res.context["consent_text"]
        self.assertEqual(shown.version, "2026-10")
        self.assertContains(res, shown.text)

    def test_without_consent_text_no_opt_in_is_offered(self):
        NewsletterConsentText.objects.all().delete()  # queryset bypasses delete()
        self.assertIsNone(NewsletterConsentText.current())
        res = self.client.get(reverse("account_profile"))
        self.assertNotContains(res, "Subscribe to newsletter")
        self.assertNotIn("newsletter_opt_in", CustomSignupForm().fields)
        self.client.post(
            reverse("account_newsletter_preference"), {"action": "subscribe"}
        )
        self.user.profile.refresh_from_db()
        self.assertFalse(self.user.profile.newsletter_opt_in)
        with self.assertRaises(ValueError):
            self.user.profile.record_opt_in(UserProfile.CONSENT_SOURCE_DASHBOARD)

    def test_export_contains_consent_text(self):
        self.user.profile.record_opt_in(UserProfile.CONSENT_SOURCE_DASHBOARD)
        self.user.profile.save()
        res = self.client.get(reverse("account_data_export"))
        payload = json.loads(
            zipfile.ZipFile(io.BytesIO(res.content)).read("account.json")
        )
        consent = payload["profile"]["newsletter_consent_text"]
        self.assertEqual(consent["version"], "2026-10")
        self.assertIn("text", consent)
        self.assertIn("newsletter_unsubscribed_at", payload["profile"])

    def test_anonymisation_removes_proof(self):
        self.user.profile.record_opt_in(UserProfile.CONSENT_SOURCE_DASHBOARD)
        self.user.profile.save()
        lifecycle.anonymize_user(self.user)
        profile = UserProfile.objects.get(pk=self.user.profile.pk)
        self.assertIsNone(profile.newsletter_consent_text)
        self.assertIsNone(profile.newsletter_opt_in_at)
