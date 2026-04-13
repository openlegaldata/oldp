"""Unit tests for OAuth well-known endpoints and DCR."""

from django.test import TestCase, override_settings
from rest_framework import status
from rest_framework.test import APIClient


@override_settings(
    CACHES={"default": {"BACKEND": "django.core.cache.backends.dummy.DummyCache"}},
    STORAGES={
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
        }
    },
)
class OAuthProtectedResourceTests(TestCase):
    """Tests for /.well-known/oauth-protected-resource endpoint."""

    def test_returns_json(self):
        response = self.client.get("/.well-known/oauth-protected-resource")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/json")

    def test_contains_required_fields(self):
        response = self.client.get("/.well-known/oauth-protected-resource")
        data = response.json()
        self.assertIn("resource", data)
        self.assertIn("authorization_servers", data)
        self.assertIn("/mcp", data["resource"])

    def test_only_get_allowed(self):
        response = self.client.post("/.well-known/oauth-protected-resource")
        self.assertEqual(response.status_code, 405)


@override_settings(
    CACHES={"default": {"BACKEND": "django.core.cache.backends.dummy.DummyCache"}},
    STORAGES={
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
        }
    },
)
class OAuthAuthorizationServerTests(TestCase):
    """Tests for /.well-known/oauth-authorization-server endpoint."""

    def test_returns_json(self):
        response = self.client.get("/.well-known/oauth-authorization-server")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/json")

    def test_contains_required_fields(self):
        response = self.client.get("/.well-known/oauth-authorization-server")
        data = response.json()
        self.assertIn("authorization_endpoint", data)
        self.assertIn("token_endpoint", data)
        self.assertIn("registration_endpoint", data)
        self.assertIn("scopes_supported", data)
        self.assertIn("code_challenge_methods_supported", data)

    def test_s256_supported(self):
        response = self.client.get("/.well-known/oauth-authorization-server")
        data = response.json()
        self.assertIn("S256", data["code_challenge_methods_supported"])


@override_settings(
    CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "dcr-tests",
        }
    },
    STORAGES={
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
        }
    },
)
class DynamicClientRegistrationTests(TestCase):
    """Tests for the DCR endpoint (RFC 7591)."""

    def setUp(self):
        from django.core.cache import cache

        cache.clear()
        self.client = APIClient()

    def test_register_public_client(self):
        response = self.client.post(
            "/oauth/register/",
            {
                "client_name": "Claude Test",
                "redirect_uris": ["https://claude.ai/callback"],
                "grant_types": ["authorization_code"],
                "token_endpoint_auth_method": "none",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        data = response.json()
        self.assertIn("client_id", data)
        self.assertEqual(data["client_name"], "Claude Test")
        self.assertNotIn("client_secret", data)

    def test_register_confidential_client(self):
        response = self.client.post(
            "/oauth/register/",
            {
                "client_name": "Confidential App",
                "redirect_uris": ["https://example.com/callback"],
                "grant_types": ["authorization_code"],
                "token_endpoint_auth_method": "client_secret_basic",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        data = response.json()
        self.assertIn("client_id", data)
        self.assertIn("client_secret", data)

    def test_register_without_redirect_uris_fails(self):
        response = self.client.post(
            "/oauth/register/",
            {
                "client_name": "Bad Client",
                "grant_types": ["authorization_code"],
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("error", response.json())
