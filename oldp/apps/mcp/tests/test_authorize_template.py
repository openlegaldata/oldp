"""Tests for the OLDP-themed OAuth consent screen (oauth2_provider/authorize.html)."""

import base64
import hashlib
import unittest
from urllib.parse import urlencode

from django.conf import settings
from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from oauth2_provider.models import get_application_model

Application = get_application_model()

REDIRECT_URI = "https://claude.ai/api/mcp/auth_callback"
CODE_CHALLENGE = (
    base64.urlsafe_b64encode(hashlib.sha256(b"x" * 64).digest()).rstrip(b"=").decode()
)
GERMAN_MO = settings.PACKAGE_DIR / "locale/de/LC_MESSAGES/django.mo"


@override_settings(
    CACHES={"default": {"BACKEND": "django.core.cache.backends.dummy.DummyCache"}},
    STORAGES={
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
        }
    },
)
class AuthorizeTemplateTests(TestCase):
    """The authorize view renders the OLDP micro layout instead of the default."""

    def setUp(self):
        self.user = User.objects.create_user("jdoe", "jdoe@example.org", "pw")
        self.app = Application.objects.create(
            name="Claude",
            client_type=Application.CLIENT_PUBLIC,
            authorization_grant_type=Application.GRANT_AUTHORIZATION_CODE,
            redirect_uris=REDIRECT_URI,
            client_secret="",
        )
        self.client.force_login(self.user)

    def authorize_url(self, **overrides):
        params = {
            "response_type": "code",
            "client_id": self.app.client_id,
            "redirect_uri": REDIRECT_URI,
            "scope": "read",
            "state": "abc",
            "code_challenge": CODE_CHALLENGE,
            "code_challenge_method": "S256",
        }
        params.update(overrides)
        return "/oauth/authorize/?" + urlencode(params)

    def test_consent_screen_uses_oldp_layout(self):
        response = self.client.get(self.authorize_url(), HTTP_HOST="localhost:8000")
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "oauth2_provider/authorize.html")
        self.assertTemplateUsed(response, "micro_layout.html")
        self.assertNotContains(response, "bootstrapcdn.com")
        self.assertContains(response, 'class="oauth-authorize"')
        self.assertContains(response, "Authorize <strong>Claude</strong>?", html=False)
        self.assertContains(response, "Read access to legal data")
        self.assertContains(response, 'name="allow"')

    def test_error_screen_uses_oldp_layout(self):
        response = self.client.get(
            self.authorize_url(client_id="doesnotexist"), HTTP_HOST="localhost:8000"
        )
        self.assertTemplateUsed(response, "micro_layout.html")
        self.assertContains(response, "Authorization error", status_code=400)
        self.assertContains(response, "invalid_request", status_code=400)

    def test_allow_redirects_with_code(self):
        url = self.authorize_url()
        response = self.client.get(url, HTTP_HOST="localhost:8000")
        form = response.context["form"]
        data = {k: v for k, v in form.initial.items() if v is not None}
        data["allow"] = "Authorize"
        response = self.client.post(url, data, HTTP_HOST="localhost:8000")
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response["Location"].startswith(REDIRECT_URI + "?code="))

    @unittest.skipUnless(GERMAN_MO.exists(), "German catalog not compiled")
    def test_consent_screen_german(self):
        # 127.0.0.1:8000 maps to "de" in LANGUAGES_DOMAINS
        response = self.client.get(self.authorize_url(), HTTP_HOST="127.0.0.1:8000")
        self.assertContains(
            response, "<strong>Claude</strong> autorisieren?", html=False
        )
        self.assertContains(response, "Lesezugriff auf juristische Daten")
        self.assertContains(response, "Angemeldet als")
        self.assertContains(response, 'value="Autorisieren"', html=False)
        self.assertContains(response, 'value="Abbrechen"', html=False)
