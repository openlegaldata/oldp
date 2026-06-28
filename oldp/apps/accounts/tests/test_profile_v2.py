from django.contrib.auth.models import User
from django.core import mail
from django.test import RequestFactory, TestCase
from django.urls import reverse

from oldp.api.throttling import TokenUserRateThrottle
from oldp.apps.accounts.adapters import CustomAccountAdapter
from oldp.apps.accounts.forms import CustomSignupForm
from oldp.apps.accounts.models import APIToken, UserProfile
from oldp.apps.accounts.newsletter import make_doi_token


class DashboardViewTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            "dashuser", "dash@example.com", "testpass123"
        )
        self.client.force_login(self.user)

    def test_dashboard_renders(self):
        res = self.client.get(reverse("account_profile"))
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "Dashboard")
        # Profile edit form present
        self.assertIn("form", res.context)

    def test_dashboard_shows_custom_rate_limit(self):
        APIToken.objects.create(user=self.user, name="prod", rate_limit=20000)
        res = self.client.get(reverse("account_profile"))
        self.assertEqual(res.context["custom_rate_limit"], 20000)

    def test_dashboard_consumption_meter_context(self):
        res = self.client.get(reverse("account_profile"))
        # Default tier => effective limit 5000, no usage recorded yet.
        self.assertEqual(res.context["effective_limit"], 5000)
        self.assertEqual(res.context["usage_used"], 0)
        self.assertEqual(res.context["usage_remaining"], 5000)
        self.assertEqual(res.context["usage_percent"], 0)

    def test_dashboard_effective_limit_uses_custom_token(self):
        APIToken.objects.create(user=self.user, name="prod", rate_limit=20000)
        res = self.client.get(reverse("account_profile"))
        self.assertEqual(res.context["effective_limit"], 20000)

    def test_profile_edit_persists(self):
        res = self.client.post(
            reverse("account_profile_edit"),
            {
                "display_name": "Dash User",
                "organization": "ACME Legal",
                "role": UserProfile.ROLE_DEVELOPER,
                "use_case": "Building a citation tool",
                "country": "DE",
            },
        )
        self.assertRedirects(res, reverse("account_profile"))
        self.user.profile.refresh_from_db()
        self.assertEqual(self.user.profile.organization, "ACME Legal")
        self.assertEqual(self.user.profile.role, UserProfile.ROLE_DEVELOPER)


class NewsletterFlowTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            "newsuser", "news@example.com", "testpass123"
        )
        self.client.force_login(self.user)

    def test_subscribe_sends_doi_and_is_not_yet_subscriber(self):
        res = self.client.post(
            reverse("account_newsletter_preference"), {"action": "subscribe"}
        )
        self.assertRedirects(res, reverse("account_profile"))
        profile = self.user.profile
        profile.refresh_from_db()
        self.assertTrue(profile.newsletter_opt_in)
        self.assertFalse(profile.is_newsletter_subscriber)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn(profile.user.email, mail.outbox[0].to)

    def test_confirm_makes_subscriber(self):
        profile = self.user.profile
        profile.record_opt_in(UserProfile.CONSENT_SOURCE_DASHBOARD)
        profile.save()

        token = make_doi_token(self.user)
        res = self.client.get(
            reverse("account_newsletter_confirm", kwargs={"token": token})
        )
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.context["confirmed"])
        profile.refresh_from_db()
        self.assertTrue(profile.is_newsletter_subscriber)

    def test_confirm_invalid_token(self):
        res = self.client.get(
            reverse("account_newsletter_confirm", kwargs={"token": "not-a-token"})
        )
        self.assertEqual(res.status_code, 200)
        self.assertFalse(res.context["confirmed"])

    def test_unsubscribe(self):
        profile = self.user.profile
        profile.record_opt_in(UserProfile.CONSENT_SOURCE_DASHBOARD)
        profile.confirm_double_opt_in()
        profile.save()
        self.assertTrue(profile.is_newsletter_subscriber)

        res = self.client.post(
            reverse("account_newsletter_preference"), {"action": "unsubscribe"}
        )
        self.assertRedirects(res, reverse("account_profile"))
        profile.refresh_from_db()
        self.assertFalse(profile.is_newsletter_subscriber)
        self.assertFalse(profile.newsletter_opt_in)


class SignupFormTestCase(TestCase):
    """The custom signup form persists profile fields via the signup() hook."""

    def _signup(self, user, data):
        form = CustomSignupForm(data=data)
        self.assertTrue(form.is_valid(), form.errors)
        request = RequestFactory().get("/accounts/signup/")
        form.signup(request, user)

    def test_signup_persists_profile_fields(self):
        user = User.objects.create_user("su1", "su1@example.com", "testpass123")
        self._signup(
            user,
            {
                "organization": "OpenLegal Inc",
                "role": UserProfile.ROLE_LEGAL_TECH,
                "use_case": "Legal research",
                "newsletter_opt_in": False,
            },
        )
        user.profile.refresh_from_db()
        self.assertEqual(user.profile.organization, "OpenLegal Inc")
        self.assertEqual(user.profile.role, UserProfile.ROLE_LEGAL_TECH)
        self.assertFalse(user.profile.newsletter_opt_in)
        self.assertEqual(len(mail.outbox), 0)

    def test_signup_with_opt_in_triggers_doi(self):
        user = User.objects.create_user("su2", "su2@example.com", "testpass123")
        self._signup(
            user,
            {
                "organization": "",
                "role": "",
                "use_case": "",
                "newsletter_opt_in": True,
            },
        )
        user.profile.refresh_from_db()
        self.assertTrue(user.profile.newsletter_opt_in)
        self.assertEqual(user.profile.consent_source, UserProfile.CONSENT_SOURCE_SIGNUP)
        self.assertFalse(user.profile.is_newsletter_subscriber)
        self.assertEqual(len(mail.outbox), 1)


class ProfileEnrichmentModelTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("enrich", "e@example.com", "testpass123")
        self.profile = self.user.profile

    def test_incomplete_by_default(self):
        self.assertFalse(self.profile.is_profile_complete)
        self.assertTrue(self.profile.is_enrichment_needed)

    def test_complete_requires_role_and_use_case(self):
        self.profile.role = UserProfile.ROLE_DEVELOPER
        self.assertFalse(self.profile.is_profile_complete)  # no use_case yet
        self.profile.use_case = "Building a tool"
        self.assertTrue(self.profile.is_profile_complete)
        self.assertFalse(self.profile.is_enrichment_needed)

    def test_prompted_suppresses_enrichment(self):
        self.profile.mark_enrichment_prompted()
        self.assertIsNotNone(self.profile.enrichment_prompted_at)
        # Even though still incomplete, no longer "needed" (asked once).
        self.assertTrue(not self.profile.is_profile_complete)
        self.assertFalse(self.profile.is_enrichment_needed)

    def test_bonus_granted_once(self):
        self.profile.role = UserProfile.ROLE_RESEARCHER
        self.profile.use_case = "Research"
        self.assertTrue(self.profile.maybe_grant_enrichment_bonus())
        self.assertIsNotNone(self.profile.enriched_at)
        # Idempotent — not granted a second time.
        self.assertFalse(self.profile.maybe_grant_enrichment_bonus())

    def test_bonus_not_granted_when_incomplete(self):
        self.profile.role = UserProfile.ROLE_OTHER  # no use_case
        self.assertFalse(self.profile.maybe_grant_enrichment_bonus())
        self.assertIsNone(self.profile.enriched_at)


class EnrichmentRedirectTestCase(TestCase):
    """The account adapter sends incomplete profiles to the enrichment prompt."""

    def setUp(self):
        self.adapter = CustomAccountAdapter()
        self.rf = RequestFactory()

    def _redirect_for(self, user):
        request = self.rf.get("/accounts/login/")
        request.user = user
        return self.adapter.get_login_redirect_url(request)

    def test_incomplete_profile_redirects_to_enrichment(self):
        user = User.objects.create_user("inc", "inc@example.com", "testpass123")
        self.assertEqual(
            self._redirect_for(user), reverse("account_profile_enrichment")
        )

    def test_complete_profile_uses_default_redirect(self):
        user = User.objects.create_user("comp", "comp@example.com", "testpass123")
        p = user.profile
        p.role = UserProfile.ROLE_DEVELOPER
        p.use_case = "x"
        p.save()
        self.assertNotEqual(
            self._redirect_for(user), reverse("account_profile_enrichment")
        )

    def test_prompted_incomplete_uses_default_redirect(self):
        user = User.objects.create_user("pr", "pr@example.com", "testpass123")
        user.profile.mark_enrichment_prompted()
        user.profile.save()
        self.assertNotEqual(
            self._redirect_for(user), reverse("account_profile_enrichment")
        )


class EnrichmentViewTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("ev", "ev@example.com", "testpass123")
        self.client.force_login(self.user)

    def test_get_renders(self):
        res = self.client.get(reverse("account_profile_enrichment"))
        self.assertEqual(res.status_code, 200)
        self.assertIn("form", res.context)

    def test_skip_marks_prompted_only(self):
        res = self.client.post(reverse("account_profile_enrichment"), {"skip": "1"})
        self.assertRedirects(res, reverse("account_profile"))
        self.user.profile.refresh_from_db()
        self.assertIsNotNone(self.user.profile.enrichment_prompted_at)
        self.assertIsNone(self.user.profile.enriched_at)

    def test_complete_grants_bonus_and_opt_in(self):
        res = self.client.post(
            reverse("account_profile_enrichment"),
            {
                "display_name": "",
                "organization": "ACME",
                "role": UserProfile.ROLE_LEGAL_TECH,
                "use_case": "Building legal AI",
                "country": "DE",
                "newsletter_opt_in": "on",
            },
        )
        self.assertRedirects(res, reverse("account_profile"))
        p = self.user.profile
        p.refresh_from_db()
        self.assertTrue(p.is_profile_complete)
        self.assertIsNotNone(p.enriched_at)
        self.assertIsNotNone(p.enrichment_prompted_at)
        self.assertTrue(p.newsletter_opt_in)
        self.assertEqual(p.consent_source, UserProfile.CONSENT_SOURCE_PROMPT)
        self.assertEqual(len(mail.outbox), 1)  # DOI email

    def test_dashboard_banner_shows_when_incomplete(self):
        res = self.client.get(reverse("account_profile"))
        self.assertContains(res, reverse("account_profile_enrichment"))


class EnrichedThrottleTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("thr", "thr@example.com", "testpass123")
        self.throttle = TokenUserRateThrottle()

    def test_not_enriched_by_default(self):
        self.assertFalse(self.throttle._user_is_enriched(self.user))

    def test_enriched_after_completion(self):
        p = self.user.profile
        p.role = UserProfile.ROLE_DEVELOPER
        p.use_case = "x"
        p.maybe_grant_enrichment_bonus()
        p.save()
        self.assertTrue(self.throttle._user_is_enriched(self.user))

    def test_enriched_scope_rate_configured(self):
        self.assertEqual(self.throttle.get_rate_for_scope("enriched"), "10000/hour")


class ApiTokenLimitTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("tok", "tok@example.com", "testpass123")
        self.client.force_login(self.user)

    def test_default_max_tokens(self):
        self.assertEqual(self.user.profile.get_max_api_tokens(), 5)

    def test_per_user_override_wins(self):
        self.user.profile.max_api_tokens = 12
        self.user.profile.save()
        self.assertEqual(self.user.profile.get_max_api_tokens(), 12)

    def test_create_blocked_at_limit(self):
        for i in range(5):
            APIToken.objects.create(user=self.user, name=f"t{i}")
        res = self.client.post(
            reverse("account_api_token_create"), {"name": "sixth", "expiration_days": 0}
        )
        self.assertRedirects(res, reverse("account_api_tokens"))
        # No 6th token created.
        self.assertEqual(APIToken.objects.filter(user=self.user).count(), 5)

    def test_create_allowed_below_limit(self):
        for i in range(4):
            APIToken.objects.create(user=self.user, name=f"t{i}")
        res = self.client.post(
            reverse("account_api_token_create"), {"name": "fifth", "expiration_days": 0}
        )
        self.assertRedirects(res, reverse("account_api_tokens"))
        self.assertEqual(APIToken.objects.filter(user=self.user).count(), 5)

    def test_admin_override_allows_more(self):
        self.user.profile.max_api_tokens = 7
        self.user.profile.save()
        for i in range(5):
            APIToken.objects.create(user=self.user, name=f"t{i}")
        res = self.client.post(
            reverse("account_api_token_create"), {"name": "sixth", "expiration_days": 0}
        )
        self.assertRedirects(res, reverse("account_api_tokens"))
        self.assertEqual(APIToken.objects.filter(user=self.user).count(), 6)

    def test_list_view_reports_limit(self):
        APIToken.objects.create(user=self.user, name="t0")
        res = self.client.get(reverse("account_api_tokens"))
        self.assertEqual(res.context["max_tokens"], 5)
        self.assertEqual(res.context["token_count"], 1)
        self.assertFalse(res.context["at_token_limit"])
