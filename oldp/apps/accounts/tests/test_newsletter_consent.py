"""Tests for the newsletter consent evidence log and its retention purge."""

import io
import json
import zipfile
from datetime import datetime
from datetime import timezone as dt_timezone

from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import RequestFactory, TestCase
from django.urls import reverse

from oldp.apps.accounts import gdpr, lifecycle
from oldp.apps.accounts.forms import CustomSignupForm
from oldp.apps.accounts.models import NewsletterConsentLog, UserProfile
from oldp.apps.accounts.newsletter import (
    CONSENT_TEXT,
    CONSENT_TEXT_VERSION,
    log_consent,
    make_doi_token,
)

PASSWORD = "testpass123"


def _rows(user=None, email=None):
    qs = NewsletterConsentLog.objects.order_by("created_at")
    if user is not None:
        qs = qs.filter(user=user)
    if email is not None:
        qs = qs.filter(email=email)
    return list(qs)


class ConsentLogFlowTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("nluser", "nl@example.com", PASSWORD)
        self.client.force_login(self.user)

    def test_dashboard_subscribe_confirm_unsubscribe_is_logged(self):
        self.client.post(
            reverse("account_newsletter_preference"), {"action": "subscribe"}
        )
        token = make_doi_token(self.user)
        self.client.get(reverse("account_newsletter_confirm", kwargs={"token": token}))
        self.client.post(
            reverse("account_newsletter_preference"), {"action": "unsubscribe"}
        )

        rows = _rows(user=self.user)
        self.assertEqual(
            [r.action for r in rows],
            [
                NewsletterConsentLog.ACTION_OPT_IN,
                NewsletterConsentLog.ACTION_CONFIRMED,
                NewsletterConsentLog.ACTION_REVOKED,
            ],
        )
        opt_in, confirmed, revoked = rows
        self.assertEqual(opt_in.email, "nl@example.com")
        self.assertEqual(opt_in.source, UserProfile.CONSENT_SOURCE_DASHBOARD)
        self.assertEqual(opt_in.consent_text, str(CONSENT_TEXT))
        self.assertEqual(opt_in.consent_text_version, CONSENT_TEXT_VERSION)
        self.assertEqual(confirmed.consent_text_version, CONSENT_TEXT_VERSION)
        # A revocation carries no wording — there is nothing to prove.
        self.assertEqual(revoked.consent_text, "")
        self.assertEqual(revoked.source, UserProfile.CONSENT_SOURCE_DASHBOARD)

        # The live state is cleared, the proof stays.
        profile = self.user.profile
        profile.refresh_from_db()
        self.assertFalse(profile.newsletter_opt_in)
        self.assertIsNone(profile.newsletter_opt_in_at)
        self.assertEqual(NewsletterConsentLog.objects.count(), 3)

    def test_unsubscribe_without_prior_consent_logs_nothing(self):
        self.client.post(
            reverse("account_newsletter_preference"), {"action": "unsubscribe"}
        )
        self.assertEqual(NewsletterConsentLog.objects.count(), 0)

    def test_confirm_is_logged_once(self):
        profile = self.user.profile
        profile.record_opt_in(UserProfile.CONSENT_SOURCE_DASHBOARD)
        profile.save()
        token = make_doi_token(self.user)
        url = reverse("account_newsletter_confirm", kwargs={"token": token})
        self.client.get(url)
        self.client.get(url)  # second click on the same link
        self.assertEqual(
            NewsletterConsentLog.objects.filter(
                action=NewsletterConsentLog.ACTION_CONFIRMED
            ).count(),
            1,
        )

    def test_signup_opt_in_is_logged_with_source(self):
        user = User.objects.create_user("su", "su@example.com", PASSWORD)
        form = CustomSignupForm(
            data={
                "organization": "",
                "role": "",
                "use_case": "",
                "newsletter_opt_in": True,
            }
        )
        self.assertTrue(form.is_valid(), form.errors)
        form.signup(RequestFactory().get("/accounts/signup/"), user)
        rows = _rows(user=user)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].action, NewsletterConsentLog.ACTION_OPT_IN)
        self.assertEqual(rows[0].source, UserProfile.CONSENT_SOURCE_SIGNUP)

    def test_export_contains_consent_log(self):
        self.client.post(
            reverse("account_newsletter_preference"), {"action": "subscribe"}
        )
        res = self.client.get(reverse("account_data_export"))
        zf = zipfile.ZipFile(io.BytesIO(res.content))
        payload = json.loads(zf.read("account.json"))
        self.assertEqual(len(payload["newsletter_consent_log"]), 1)
        entry = payload["newsletter_consent_log"][0]
        self.assertEqual(entry["action"], NewsletterConsentLog.ACTION_OPT_IN)
        self.assertEqual(entry["consent_text_version"], CONSENT_TEXT_VERSION)


class ConsentLogSurvivesAccountRemovalTests(TestCase):
    def _subscribed_user(self, name):
        user = User.objects.create_user(name, f"{name}@example.com", PASSWORD)
        profile = user.profile
        profile.record_opt_in(UserProfile.CONSENT_SOURCE_DASHBOARD)
        profile.confirm_double_opt_in()
        profile.save()
        log_consent(profile, NewsletterConsentLog.ACTION_OPT_IN, profile.consent_source)
        log_consent(
            profile, NewsletterConsentLog.ACTION_CONFIRMED, profile.consent_source
        )
        return user

    def test_hard_delete_keeps_rows_and_logs_revocation(self):
        user = self._subscribed_user("delme")
        gdpr.delete_user_account(user)
        rows = _rows(email="delme@example.com")
        self.assertEqual(len(rows), 3)
        self.assertTrue(all(r.user_id is None for r in rows))
        self.assertEqual(rows[-1].action, NewsletterConsentLog.ACTION_REVOKED)
        self.assertEqual(rows[-1].source, NewsletterConsentLog.SOURCE_ACCOUNT_DELETION)

    def test_hard_delete_without_consent_logs_nothing(self):
        user = User.objects.create_user("plain", "plain@example.com", PASSWORD)
        gdpr.delete_user_account(user)
        self.assertEqual(NewsletterConsentLog.objects.count(), 0)

    def test_lifecycle_anonymisation_logs_revocation_with_old_email(self):
        user = self._subscribed_user("dormant")
        lifecycle.anonymize_user(user)
        rows = _rows(email="dormant@example.com")
        self.assertEqual(rows[-1].action, NewsletterConsentLog.ACTION_REVOKED)
        self.assertEqual(rows[-1].source, NewsletterConsentLog.SOURCE_LIFECYCLE)
        self.assertEqual(rows[-1].user_id, user.pk)
        user.refresh_from_db()
        self.assertEqual(user.email, "")


class PurgeConsentLogsTests(TestCase):
    def _chain(self, email, revoked_at, user=None):
        base = dict(user=user, email=email, consent_text="x", consent_text_version="v")
        NewsletterConsentLog.objects.create(
            action=NewsletterConsentLog.ACTION_OPT_IN,
            created_at=revoked_at.replace(year=revoked_at.year - 1),
            **base,
        )
        NewsletterConsentLog.objects.create(
            action=NewsletterConsentLog.ACTION_REVOKED,
            created_at=revoked_at,
            user=user,
            email=email,
        )

    def test_purges_only_expired_chains(self):
        now = datetime.now(dt_timezone.utc)
        expired = datetime(now.year - 4, 6, 1, tzinfo=dt_timezone.utc)
        boundary = datetime(now.year - 3, 12, 31, tzinfo=dt_timezone.utc)
        recent = datetime(now.year - 1, 1, 1, tzinfo=dt_timezone.utc)
        self._chain("old@example.com", expired)
        self._chain("boundary@example.com", boundary)
        self._chain("new@example.com", recent)

        out = io.StringIO()
        call_command("purge_newsletter_consent_logs", stdout=out)

        self.assertEqual(_rows(email="old@example.com"), [])
        # Revoked in year now-3: expires 1 Jan of (now-3)+4 = next year — kept.
        self.assertEqual(len(_rows(email="boundary@example.com")), 2)
        self.assertEqual(len(_rows(email="new@example.com")), 2)
        self.assertIn("Deleted 2", out.getvalue())

    def test_resubscription_after_revocation_is_kept(self):
        now = datetime.now(dt_timezone.utc)
        expired = datetime(now.year - 5, 3, 1, tzinfo=dt_timezone.utc)
        self._chain("back@example.com", expired)
        NewsletterConsentLog.objects.create(
            email="back@example.com",
            action=NewsletterConsentLog.ACTION_OPT_IN,
            created_at=datetime(now.year - 1, 2, 1, tzinfo=dt_timezone.utc),
        )
        call_command("purge_newsletter_consent_logs", stdout=io.StringIO())
        rows = _rows(email="back@example.com")
        self.assertEqual([r.action for r in rows], [NewsletterConsentLog.ACTION_OPT_IN])
        self.assertEqual(rows[0].created_at.year, now.year - 1)

    def test_dry_run_deletes_nothing(self):
        now = datetime.now(dt_timezone.utc)
        self._chain(
            "dry@example.com", datetime(now.year - 6, 1, 1, tzinfo=dt_timezone.utc)
        )
        out = io.StringIO()
        call_command("purge_newsletter_consent_logs", "--dry-run", stdout=out)
        self.assertEqual(len(_rows(email="dry@example.com")), 2)
        self.assertIn("Would delete 2", out.getvalue())
