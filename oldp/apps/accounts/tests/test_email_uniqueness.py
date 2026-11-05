"""One email address per account: DB indexes, allauth flows, admin, command."""

import importlib
from io import StringIO

from allauth.account.models import EmailAddress, EmailConfirmationHMAC
from django.apps import apps as django_apps
from django.contrib.auth.models import User
from django.core import mail
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import IntegrityError, connection, transaction
from django.test import TestCase, override_settings, skipUnlessDBFeature

from oldp.apps.accounts.email_uniqueness import (
    find_duplicate_emails,
    find_unverified_claims,
    holders_of_email,
    is_email_taken,
)

migration_0015 = importlib.import_module(
    "oldp.apps.accounts.migrations.0015_unique_email_indexes"
)

PASSWORD = "S3cure-pass-xyz!"
ALLAUTH_INDEX_DROP = "DROP INDEX IF EXISTS unique_verified_email"


def make_user(username, email, verified=None, primary=True):
    """Create a user; with ``verified`` set also its allauth EmailAddress."""
    user = User.objects.create_user(username, email, PASSWORD)
    if verified is not None:
        EmailAddress.objects.create(
            user=user, email=email.lower(), primary=primary, verified=verified
        )
    return user


class DatabaseIndexTestCase(TestCase):
    """Migration 0015 indexes (partial indexes on SQLite/PostgreSQL)."""

    def test_user_email_unique(self):
        make_user("alice", "shared@example.com")
        with self.assertRaises(IntegrityError), transaction.atomic():
            make_user("bob", "shared@example.com")

    def test_user_email_unique_ignores_case(self):
        make_user("alice", "shared@example.com")
        bob = make_user("bob", "bob@example.com")
        # update() bypasses the lowercasing pre_save signal.
        with self.assertRaises(IntegrityError), transaction.atomic():
            User.objects.filter(pk=bob.pk).update(email="SHARED@example.com")

    def test_blank_user_emails_allowed(self):
        make_user("alice", "")
        make_user("bob", "")
        self.assertEqual(User.objects.filter(email="").count(), 2)

    def test_verified_email_address_unique(self):
        make_user("alice", "shared@example.com", verified=True)
        bob = make_user("bob", "bob@example.com", verified=True)
        with self.assertRaises(IntegrityError), transaction.atomic():
            EmailAddress.objects.create(
                user=bob, email="shared@example.com", primary=False, verified=True
            )

    def test_unverified_email_address_duplicates_allowed(self):
        make_user("alice", "shared@example.com", verified=True)
        bob = make_user("bob", "bob@example.com", verified=True)
        EmailAddress.objects.create(
            user=bob, email="shared@example.com", primary=False, verified=False
        )
        self.assertEqual(
            EmailAddress.objects.filter(email="shared@example.com").count(), 2
        )


class NormalizationTestCase(TestCase):
    def test_user_email_is_lowercased(self):
        user = make_user("alice", " Alice@Example.COM ")
        user.refresh_from_db()
        self.assertEqual(user.email, "alice@example.com")


class IsEmailTakenTestCase(TestCase):
    def test_user_email_of_other_account(self):
        alice = make_user("alice", "shared@example.com")
        bob = make_user("bob", "bob@example.com")
        self.assertTrue(is_email_taken("SHARED@example.com", bob))
        self.assertFalse(is_email_taken("shared@example.com", alice))

    def test_verified_address_of_other_account(self):
        alice = make_user("alice", "alice@example.com", verified=True)
        EmailAddress.objects.create(
            user=alice, email="second@example.com", primary=False, verified=True
        )
        bob = make_user("bob", "bob@example.com")
        self.assertTrue(is_email_taken("second@example.com", bob))

    def test_unverified_secondary_address_does_not_count(self):
        alice = make_user("alice", "alice@example.com", verified=True)
        EmailAddress.objects.create(
            user=alice, email="claimed@example.com", primary=False, verified=False
        )
        bob = make_user("bob", "bob@example.com")
        self.assertFalse(is_email_taken("claimed@example.com", bob))

    def test_blank(self):
        self.assertFalse(is_email_taken(""))
        self.assertFalse(is_email_taken(None))


@override_settings(ACCOUNT_RATE_LIMITS=False)
class AllauthFlowTestCase(TestCase):
    def setUp(self):
        self.alice = make_user("alice", "shared@example.com", verified=False)
        self.bob = make_user("bob", "bob@example.com", verified=True)

    def test_signup_with_taken_email_creates_no_account(self):
        res = self.client.post(
            "/accounts/signup/",
            {
                "username": "carol",
                "email": "SHARED@example.com",
                "password1": PASSWORD,
                "password2": PASSWORD,
            },
        )
        self.assertEqual(res.status_code, 302)
        self.assertFalse(User.objects.filter(username="carol").exists())
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("Already Exists", mail.outbox[0].subject)

    def test_add_email_of_other_account_is_refused(self):
        self.client.force_login(self.bob)
        res = self.client.post(
            "/accounts/email/", {"action_add": "", "email": "Shared@example.com"}
        )
        self.assertEqual(res.status_code, 200)
        self.assertIn("email", res.context["form"].errors)
        self.assertFalse(
            EmailAddress.objects.filter(
                user=self.bob, email="shared@example.com"
            ).exists()
        )

    def test_add_free_email_still_works(self):
        self.client.force_login(self.bob)
        res = self.client.post(
            "/accounts/email/", {"action_add": "", "email": "new@example.com"}
        )
        self.assertEqual(res.status_code, 302)
        self.assertTrue(
            EmailAddress.objects.filter(user=self.bob, email="new@example.com").exists()
        )

    def test_confirming_taken_email_is_refused(self):
        # An unverified row created before the add-email check existed.
        address = EmailAddress.objects.create(
            user=self.bob, email="shared@example.com", primary=False, verified=False
        )
        key = EmailConfirmationHMAC(address).key
        self.client.force_login(self.bob)
        self.client.post(f"/accounts/confirm-email/{key}/")
        address.refresh_from_db()
        self.assertFalse(address.verified)
        self.bob.refresh_from_db()
        self.assertEqual(self.bob.email, "bob@example.com")

    def test_confirming_own_email_still_works(self):
        address = EmailAddress.objects.get(user=self.alice)
        key = EmailConfirmationHMAC(address).key
        self.client.post(f"/accounts/confirm-email/{key}/")
        address.refresh_from_db()
        self.assertTrue(address.verified)


class AdminTestCase(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser("root", "root@example.com", PASSWORD)
        self.client.force_login(self.admin)
        make_user("alice", "shared@example.com")

    def _add(self, username, email):
        return self.client.post(
            "/admin/auth/user/add/",
            {
                "username": username,
                "email": email,
                "usable_password": "true",
                "password1": PASSWORD,
                "password2": PASSWORD,
                "profile-TOTAL_FORMS": "0",
                "profile-INITIAL_FORMS": "0",
            },
        )

    def _change(self, user, email):
        return self.client.post(
            f"/admin/auth/user/{user.pk}/change/",
            {
                "username": user.username,
                "email": email,
                "date_joined_0": "2026-01-01",
                "date_joined_1": "00:00:00",
                "is_active": "on",
                "profile-TOTAL_FORMS": "1",
                "profile-INITIAL_FORMS": "1",
                "profile-MIN_NUM_FORMS": "0",
                "profile-MAX_NUM_FORMS": "1",
                "profile-0-id": user.profile.pk,
                "profile-0-user": user.pk,
            },
        )

    def test_add_user_with_taken_email_is_refused(self):
        res = self._add("eve", "SHARED@example.com")
        self.assertEqual(res.status_code, 200)
        self.assertIn("email", res.context["adminform"].form.errors)
        self.assertFalse(User.objects.filter(username="eve").exists())

    def test_add_user_with_free_email(self):
        res = self._add("eve", "Eve@Example.com")
        self.assertEqual(res.status_code, 302)
        self.assertEqual(User.objects.get(username="eve").email, "eve@example.com")

    def test_change_user_to_taken_email_is_refused(self):
        eve = make_user("eve", "eve@example.com")
        res = self._change(eve, "shared@example.com")
        self.assertEqual(res.status_code, 200)
        self.assertIn("email", res.context["adminform"].form.errors)
        eve.refresh_from_db()
        self.assertEqual(eve.email, "eve@example.com")

    def test_change_user_keeping_own_email(self):
        eve = make_user("eve", "eve@example.com")
        res = self._change(eve, "eve@example.com")
        self.assertEqual(res.status_code, 302)


class FindDuplicatesTestCase(TestCase):
    def _run(self, *args):
        out = StringIO()
        call_command("find_duplicate_emails", *args, stdout=out)
        return out.getvalue()

    def test_no_duplicates(self):
        make_user("alice", "alice@example.com", verified=True)
        output = self._run("--check")
        self.assertIn("DUPLICATES_TOTAL=0", output)

    def test_cross_duplicate(self):
        # Not covered by an index: alice's user.email is bob's verified address.
        make_user("alice", "shared@example.com", verified=False)
        bob = make_user("bob", "bob@example.com", verified=True)
        EmailAddress.objects.create(
            user=bob, email="shared@example.com", primary=False, verified=True
        )
        self.assertEqual(find_duplicate_emails()["cross"], ["shared@example.com"])
        output = self._run()
        self.assertIn("shared@example.com", output)
        self.assertIn("alice", output)
        self.assertIn("bob", output)
        self.assertIn("DUPLICATES_TOTAL=1", output)
        with self.assertRaises(CommandError):
            self._run("--check")


@skipUnlessDBFeature("supports_partial_indexes")
class LegacyDuplicatesTestCase(TestCase):
    """Duplicates that exist from before the indexes (indexes dropped here)."""

    def setUp(self):
        with connection.cursor() as cursor:
            # Also allauth's own partial index, which exists on these backends.
            for sql in [*migration_0015.PARTIAL_REVERSE, ALLAUTH_INDEX_DROP]:
                cursor.execute(sql)
        make_user("alice", "shared@example.com", verified=True)
        make_user("bob", "shared@example.com", verified=True)

    def test_reported(self):
        found = find_duplicate_emails()
        self.assertEqual(found["user_email"], ["shared@example.com"])
        self.assertEqual(found["verified_email_address"], ["shared@example.com"])

    def test_migration_refuses_to_run(self):
        with self.assertRaisesMessage(RuntimeError, "find_duplicate_emails"):
            migration_0015._check_no_duplicates(django_apps, "default")


@override_settings(ACCOUNT_RATE_LIMITS=False)
class UnverifiedClaimTestCase(TestCase):
    """Another account added the address but never confirmed it."""

    def setUp(self):
        self.bob = make_user("bob", "bob@example.com", verified=True)
        EmailAddress.objects.create(
            user=self.bob, email="x@example.com", primary=False, verified=False
        )

    def test_claim_does_not_hold_the_address(self):
        self.assertFalse(holders_of_email("x@example.com").exists())
        self.assertEqual(list(holders_of_email("bob@example.com")), [self.bob])

    def test_owner_can_sign_up(self):
        self.client.post(
            "/accounts/signup/",
            {
                "username": "xowner",
                "email": "x@example.com",
                "password1": PASSWORD,
                "password2": PASSWORD,
            },
        )
        owner = User.objects.get(username="xowner")
        self.assertEqual(owner.email, "x@example.com")
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("Confirm", mail.outbox[0].subject)

        # The owner confirms; bob's stale claim can no longer be confirmed.
        address = EmailAddress.objects.get(user=owner)
        self.client.post(
            f"/accounts/confirm-email/{EmailConfirmationHMAC(address).key}/"
        )
        address.refresh_from_db()
        self.assertTrue(address.verified)
        claim = EmailAddress.objects.get(user=self.bob, email="x@example.com")
        self.client.post(f"/accounts/confirm-email/{EmailConfirmationHMAC(claim).key}/")
        claim.refresh_from_db()
        self.assertFalse(claim.verified)

    def test_password_reset_skips_claiming_account(self):
        self.client.post("/accounts/password/reset/", {"email": "x@example.com"})
        self.assertEqual(len(mail.outbox), 1)
        self.assertNotIn("Password Reset", mail.outbox[0].subject)
        self.assertNotIn("bob", mail.outbox[0].body)

    def test_password_reset_for_unconfirmed_signup_still_works(self):
        make_user("carol", "carol@example.com", verified=False)
        self.client.post("/accounts/password/reset/", {"email": "carol@example.com"})
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("Password Reset", mail.outbox[0].subject)
        self.assertIn("carol", mail.outbox[0].body)

    def test_command_lists_and_deletes_claims_held_by_others(self):
        make_user("xowner", "x@example.com", verified=True)
        # A claim nobody else holds is left alone.
        EmailAddress.objects.create(
            user=self.bob, email="free@example.com", primary=False, verified=False
        )
        self.assertEqual(
            [(c.user, c.email) for c in find_unverified_claims()],
            [(self.bob, "x@example.com")],
        )
        out = StringIO()
        call_command("find_duplicate_emails", stdout=out)
        self.assertIn("unverified claim", out.getvalue())
        self.assertIn("DUPLICATES_TOTAL=1", out.getvalue())

        out = StringIO()
        call_command("find_duplicate_emails", "--delete-unverified-claims", stdout=out)
        self.assertIn("Deleting unverified claim of x@example.com", out.getvalue())
        self.assertIn("DUPLICATES_TOTAL=0", out.getvalue())
        self.assertFalse(
            EmailAddress.objects.filter(user=self.bob, email="x@example.com").exists()
        )
        self.assertTrue(
            EmailAddress.objects.filter(
                user=self.bob, email="free@example.com"
            ).exists()
        )
