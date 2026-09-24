"""Tests for the aggregate user statistics (``user_stats`` command)."""

import json
from datetime import date, datetime
from datetime import timezone as dt_timezone
from io import StringIO

from allauth.account.models import EmailAddress
from allauth.socialaccount.models import SocialAccount
from django.contrib.auth.models import User
from django.core.management import CommandError, call_command
from django.test import SimpleTestCase, TestCase, override_settings

from oldp.apps.accounts.models import APIToken, UserProfile
from oldp.apps.accounts.stats import email_category, user_stats

SINCE = date(2026, 9, 1)
UNTIL = date(2026, 9, 30)


def at(day, hour=12):
    return datetime(2026, 9, day, hour, tzinfo=dt_timezone.utc)


def make_user(
    username, joined, *, verified=False, last_login=None, email=None, **profile
):
    email = email or f"{username}@example.com"
    user = User.objects.create_user(username, email, "pass12345")
    User.objects.filter(pk=user.pk).update(date_joined=joined, last_login=last_login)
    if verified:
        EmailAddress.objects.create(user=user, email=email, verified=True, primary=True)
    if profile:
        UserProfile.objects.filter(user=user).update(**profile)
    return user


class EmailCategoryTests(SimpleTestCase):
    def test_categories(self):
        for email, category in [
            ("a@gmail.com", "freemail"),
            ("a@WEB.DE", "freemail"),
            ("a@uni-koeln.de", "academic"),
            ("a@stud.tu-berlin.de", "academic"),
            ("a@mit.edu", "academic"),
            ("a@ox.ac.uk", "academic"),
            ("a@kanzlei.de", "other"),
            ("", "none"),
        ]:
            with self.subTest(email=email):
                self.assertEqual(email_category(email), category)


@override_settings(TIME_ZONE="UTC")
class UserStatsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        # Three signups in September: one fully onboarded, one social, one spam.
        cls.alice = make_user(
            "alice",
            at(3),
            verified=True,
            last_login=at(20),
            email="alice@uni-koeln.de",
            role=UserProfile.ROLE_RESEARCHER,
            use_case="Citation network of BGH decisions",
            organization="Uni Köln",
            country="DE",
            newsletter_opt_in=True,
            newsletter_opt_in_at=at(3),
            newsletter_doi_confirmed_at=at(4),
            consent_source=UserProfile.CONSENT_SOURCE_SIGNUP,
        )
        cls.bob = make_user(
            "bob", at(10), verified=True, last_login=at(10), email="bob@gmail.com"
        )
        SocialAccount.objects.create(user=cls.bob, provider="github", uid="1")
        make_user("spam", at(15))
        # An older user who came back in September, and one from August.
        make_user(
            "carol",
            datetime(2025, 1, 1, tzinfo=dt_timezone.utc),
            verified=True,
            last_login=at(25),
        )
        make_user("dave", datetime(2026, 8, 20, tzinfo=dt_timezone.utc), verified=True)
        # Staff never counts.
        staff = make_user("admin", at(5), verified=True, last_login=at(5))
        User.objects.filter(pk=staff.pk).update(is_staff=True)

        token = APIToken.objects.create(user=cls.alice, name="t")
        APIToken.objects.filter(pk=token.pk).update(created=at(5), last_used=at(6))

    def stats(self, **kwargs):
        return user_stats(SINCE, UNTIL, **kwargs)

    def test_signups_and_activation(self):
        current = self.stats()["current"]
        self.assertEqual(current["signups"]["total"], 3)
        self.assertEqual(current["signups"]["by_method"], {"password": 2, "github": 1})
        self.assertEqual(
            current["signups"]["by_email_category"],
            {"academic": 1, "freemail": 1, "other": 1},
        )
        self.assertEqual(current["activation"]["activated"], 2)
        self.assertEqual(current["activation"]["activation_ratio"], round(2 / 3, 4))

    def test_funnel(self):
        funnel = {
            row["step"]: row["users"] for row in self.stats()["current"]["funnel"]
        }
        self.assertEqual(
            funnel,
            {
                "signed_up": 3,
                "email_verified": 2,
                "logged_in": 2,
                "api_token_created": 1,
                "api_token_used": 1,
                "mcp_connected": 0,
            },
        )

    def test_logins_split_new_and_returning(self):
        logins = self.stats()["current"]["logins"]
        self.assertEqual(logins["users_last_login_in_range"], 3)
        self.assertEqual(logins["returning_users"], 1)
        self.assertEqual(logins["new_users"], 2)

    def test_newsletter_and_profile(self):
        current = self.stats()["current"]
        self.assertEqual(current["newsletter"]["opt_ins_requested"], 1)
        self.assertEqual(current["newsletter"]["opt_ins_by_source"], {"signup": 1})
        self.assertEqual(current["newsletter"]["double_opt_ins_confirmed"], 1)
        self.assertEqual(current["newsletter"]["signups_subscribed"], 1)
        self.assertEqual(current["profile"]["signups_complete"], 1)
        self.assertEqual(
            current["profile"]["signups_field_fill"]["use_case"]["users"], 1
        )
        self.assertEqual(
            current["profile"]["signups_by_role"], {"(empty)": 2, "researcher": 1}
        )

    def test_api(self):
        api = self.stats()["current"]["api"]
        self.assertEqual(api["tokens_created"], 1)
        self.assertEqual(api["users_using_tokens"], 1)

    def test_previous_period_and_totals(self):
        report = self.stats()
        self.assertEqual(report["range"]["previous_since"], "2026-08-02")
        self.assertEqual(report["range"]["previous_until"], "2026-08-31")
        self.assertEqual(report["previous"]["signups"]["total"], 1)
        self.assertEqual(report["totals"]["users"], 5)
        self.assertEqual(report["totals"]["newsletter_subscribers"], 1)
        self.assertEqual(report["totals"]["social_login"], 1)

    def test_weekly_series_adds_up(self):
        weekly = self.stats()["weekly_signups"]
        self.assertEqual(sum(row["signups"] for row in weekly), 3)

    def test_free_text_is_opt_in_and_anonymous(self):
        self.assertNotIn("free_text", self.stats())
        rows = self.stats(include_free_text=True)["free_text"]
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["use_case"], "Citation network of BGH decisions")
        self.assertEqual(row["email_category"], "academic")
        self.assertNotIn("alice", json.dumps(rows))

    def test_free_text_includes_older_users_who_enriched(self):
        make_user(
            "erin",
            datetime(2025, 1, 1, tzinfo=dt_timezone.utc),
            use_case="Legal chatbot",
            enriched_at=at(12),
        )
        rows = self.stats(include_free_text=True)["free_text"]
        erin = [r for r in rows if r["use_case"] == "Legal chatbot"]
        self.assertEqual(len(erin), 1)
        self.assertFalse(erin[0]["joined_in_range"])


@override_settings(TIME_ZONE="UTC")
class UserStatsCommandTests(TestCase):
    def test_outputs_json(self):
        out = StringIO()
        call_command(
            "user_stats", "--since", "2026-09-01", "--until", "2026-09-30", stdout=out
        )
        report = json.loads(out.getvalue())
        self.assertEqual(report["range"]["since"], "2026-09-01")
        self.assertIn("funnel", report["current"])

    def test_days_default(self):
        out = StringIO()
        call_command("user_stats", "--until", "2026-09-30", "--days", "7", stdout=out)
        self.assertEqual(json.loads(out.getvalue())["range"]["since"], "2026-09-24")

    def test_rejects_inverted_range(self):
        with self.assertRaises(CommandError):
            call_command("user_stats", "--since", "2026-09-30", "--until", "2026-09-01")

    def test_rejects_bad_date(self):
        with self.assertRaises(CommandError):
            call_command("user_stats", "--since", "yesterday")
