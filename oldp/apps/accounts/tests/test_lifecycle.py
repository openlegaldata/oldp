"""Tests for the inactive-account lifecycle (warn -> deactivate -> anonymize)."""

from datetime import date, timedelta

from allauth.account.models import EmailAddress
from django.contrib.auth.models import User
from django.core import mail
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone

from oldp.apps.accounts import lifecycle
from oldp.apps.accounts.models import APIToken

PASSWORD = "pass12345"


def make_user(
    username,
    *,
    verified=True,
    last_login_days_ago=None,
    joined_days_ago=400,
    email=None,
):
    """Create a user with controllable activity timestamps + verification."""
    email = email or f"{username}@example.com"
    user = User.objects.create_user(username, email, PASSWORD)
    updates = {}
    if joined_days_ago is not None:
        updates["date_joined"] = timezone.now() - timedelta(days=joined_days_ago)
    if last_login_days_ago is not None:
        updates["last_login"] = timezone.now() - timedelta(days=last_login_days_ago)
    if updates:
        User.objects.filter(pk=user.pk).update(**updates)
    if verified:
        EmailAddress.objects.create(user=user, email=email, verified=True, primary=True)
    user.refresh_from_db()
    return user


@override_settings(INACTIVE_USER_DORMANCY_DAYS=365)
class SelectionTests(TestCase):
    def test_dormant_verified_user_selected(self):
        u = make_user("dormant", last_login_days_ago=400)
        self.assertIn(u, lifecycle.users_to_warn())

    def test_recent_login_excluded(self):
        u = make_user("active", last_login_days_ago=10)
        self.assertNotIn(u, lifecycle.users_to_warn())

    def test_never_logged_in_old_signup_selected(self):
        u = make_user("oldsignup", last_login_days_ago=None, joined_days_ago=400)
        self.assertIn(u, lifecycle.users_to_warn())

    def test_never_logged_in_recent_signup_excluded(self):
        u = make_user("newsignup", last_login_days_ago=None, joined_days_ago=10)
        self.assertNotIn(u, lifecycle.users_to_warn())

    def test_unverified_excluded(self):
        u = make_user("unverified", verified=False, last_login_days_ago=400)
        self.assertNotIn(u, lifecycle.users_to_warn())

    def test_staff_excluded(self):
        u = make_user("staffy", last_login_days_ago=400)
        User.objects.filter(pk=u.pk).update(is_staff=True)
        u.refresh_from_db()
        self.assertNotIn(u, lifecycle.users_to_warn())

    def test_paying_user_excluded(self):
        u = make_user("payer", last_login_days_ago=400)
        APIToken.objects.create(user=u, name="paid", rate_limit=99999)
        self.assertNotIn(u, lifecycle.users_to_warn())

    def test_custom_token_cap_excluded(self):
        u = make_user("vip", last_login_days_ago=400)
        u.profile.max_api_tokens = 50
        u.profile.save()
        self.assertNotIn(u, lifecycle.users_to_warn())

    def test_recent_token_use_excluded(self):
        u = make_user("apiuser", last_login_days_ago=400)
        APIToken.objects.create(user=u, name="t", last_used=timezone.now())
        self.assertNotIn(u, lifecycle.users_to_warn())

    def test_already_warned_excluded(self):
        u = make_user("warned", last_login_days_ago=400)
        u.profile.deletion_warning_sent_at = timezone.now()
        u.profile.save()
        self.assertNotIn(u, lifecycle.users_to_warn())


@override_settings(INACTIVE_USER_DORMANCY_DAYS=365, INACTIVE_USER_WARNING_GRACE_DAYS=90)
class WarnCommandTests(TestCase):
    def test_dry_run_changes_nothing(self):
        u = make_user("d", last_login_days_ago=400)
        call_command("warn_inactive_users", "--dry-run")
        self.assertEqual(len(mail.outbox), 0)
        u.profile.refresh_from_db()
        self.assertIsNone(u.profile.deletion_warning_sent_at)

    def test_warns_and_records_deadline(self):
        u = make_user("d", last_login_days_ago=400)
        call_command("warn_inactive_users", "--batch-delay", "0")
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn(u.email, mail.outbox[0].to)
        u.profile.refresh_from_db()
        self.assertIsNotNone(u.profile.deletion_warning_sent_at)
        self.assertIsNotNone(u.profile.deletion_scheduled_for)

    def test_email_is_bilingual(self):
        make_user("d", last_login_days_ago=400)
        call_command("warn_inactive_users", "--batch-delay", "0")
        body = mail.outbox[0].body
        self.assertIn("Hallo", body)
        self.assertIn("löschen", body)
        self.assertIn("Hello", body)
        self.assertIn("delete", body)

    def test_not_warned_twice(self):
        make_user("d", last_login_days_ago=400)
        call_command("warn_inactive_users", "--batch-delay", "0")
        call_command("warn_inactive_users", "--batch-delay", "0")
        self.assertEqual(len(mail.outbox), 1)

    def test_limit(self):
        make_user("a", last_login_days_ago=400)
        make_user("b", last_login_days_ago=400)
        call_command("warn_inactive_users", "--batch-delay", "0", "--limit", "1")
        self.assertEqual(len(mail.outbox), 1)


class LoginCancelsDeletionTests(TestCase):
    def test_login_clears_pending_warning(self):
        u = make_user("d", last_login_days_ago=400)
        u.profile.deletion_warning_sent_at = timezone.now()
        u.profile.deletion_scheduled_for = timezone.now() + timedelta(days=90)
        u.profile.save()

        self.assertTrue(self.client.login(username="d", password=PASSWORD))
        u.profile.refresh_from_db()
        self.assertIsNone(u.profile.deletion_warning_sent_at)
        self.assertIsNone(u.profile.deletion_scheduled_for)


@override_settings(INACTIVE_USER_DEACTIVATION_GRACE_DAYS=90)
class PurgeCommandTests(TestCase):
    def _warned(self, username, *, scheduled_days_ago):
        u = make_user(username, last_login_days_ago=400)
        p = u.profile
        p.deletion_warning_sent_at = timezone.now() - timedelta(days=100)
        p.deletion_scheduled_for = timezone.now() - timedelta(days=scheduled_days_ago)
        p.save()
        return u

    def test_deactivate_past_deadline(self):
        u = self._warned("d", scheduled_days_ago=10)
        call_command("purge_inactive_users")
        u.refresh_from_db()
        u.profile.refresh_from_db()
        self.assertFalse(u.is_active)
        self.assertIsNotNone(u.profile.deactivated_at)

    def test_deactivate_dry_run(self):
        u = self._warned("d", scheduled_days_ago=10)
        call_command("purge_inactive_users", "--dry-run")
        u.refresh_from_db()
        self.assertTrue(u.is_active)
        self.assertIsNone(u.profile.deactivated_at)

    def test_not_deactivated_before_deadline(self):
        u = make_user("future", last_login_days_ago=400)
        u.profile.deletion_warning_sent_at = timezone.now()
        u.profile.deletion_scheduled_for = timezone.now() + timedelta(days=30)
        u.profile.save()
        call_command("purge_inactive_users")
        u.refresh_from_db()
        self.assertTrue(u.is_active)

    def test_anonymize_after_grace(self):
        u = make_user("d", last_login_days_ago=400, email="real@example.com")
        User.objects.filter(pk=u.pk).update(is_active=False)
        u.profile.deactivated_at = timezone.now() - timedelta(days=100)
        u.profile.save()

        call_command("purge_inactive_users", "--anonymize-only")
        u.refresh_from_db()
        u.profile.refresh_from_db()
        self.assertEqual(u.username, f"deleted_{u.pk}")
        self.assertEqual(u.email, "")
        self.assertFalse(u.has_usable_password())
        self.assertIsNotNone(u.profile.anonymized_at)
        self.assertFalse(EmailAddress.objects.filter(user=u).exists())

    def test_anonymize_not_before_grace(self):
        u = make_user("d", last_login_days_ago=400)
        User.objects.filter(pk=u.pk).update(is_active=False)
        u.profile.deactivated_at = timezone.now() - timedelta(days=10)
        u.profile.save()

        call_command("purge_inactive_users", "--anonymize-only")
        u.refresh_from_db()
        u.profile.refresh_from_db()
        self.assertEqual(u.username, "d")
        self.assertIsNone(u.profile.anonymized_at)


class AnonymizeKeepsContentTests(TestCase):
    def test_content_survives_and_attribution_kept(self):
        from oldp.apps.cases.models import Case
        from oldp.apps.courts.models import Country, Court, State

        country = Country.objects.create(name="Testcountry", code="de")
        state = State.objects.create(name="Testland", slug="testland", country=country)
        court = Court.objects.create(
            name="Testgericht", code="TESTG", slug="testgericht", state=state
        )
        u = make_user("d", last_login_days_ago=400)
        token = APIToken.objects.create(user=u, name="t")
        case = Case.objects.create(
            court=court,
            file_number="LIFECYCLE-1",
            date=date(2020, 1, 1),
            content="<p>kept</p>",
            created_by_token=token,
        )

        lifecycle.anonymize_user(u)

        case.refresh_from_db()
        token.refresh_from_db()
        # Content row survives, attribution chain intact, token disabled.
        self.assertTrue(Case.objects.filter(pk=case.pk).exists())
        self.assertEqual(case.created_by_token_id, token.pk)
        self.assertFalse(token.is_active)
