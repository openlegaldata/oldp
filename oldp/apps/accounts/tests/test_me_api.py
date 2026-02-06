from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from oldp.apps.accounts.models import APIToken


class MeApiTestCase(TestCase):
    """Tests for the /api/me/ endpoint."""

    def setUp(self):
        self.user = User.objects.create_user(
            "testuser", "test@example.com", "testpassword", is_staff=True
        )
        self.client = APIClient()

    def test_unauthenticated_returns_401(self):
        res = self.client.get("/api/me/")
        self.assertEqual(res.status_code, 401)

    def test_session_auth_returns_user_info(self):
        self.client.login(username="testuser", password="testpassword")
        res = self.client.get("/api/me/")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["id"], self.user.id)
        self.assertEqual(data["username"], "testuser")
        self.assertEqual(data["email"], "test@example.com")
        self.assertTrue(data["is_staff"])
        self.assertFalse(data["is_superuser"])
        self.assertEqual(data["auth_type"], "session")
        self.assertNotIn("token", data)

    def test_token_auth_returns_user_info(self):
        # Token is auto-created by signal on user creation
        token = Token.objects.get(user=self.user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
        res = self.client.get("/api/me/")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["username"], "testuser")
        self.assertEqual(data["auth_type"], "token")
        self.assertNotIn("token", data)

    def test_api_token_auth_returns_token_details(self):
        api_token = APIToken.objects.create(
            user=self.user,
            name="Test Token",
        )
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {api_token.key}")
        res = self.client.get("/api/me/")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["username"], "testuser")
        self.assertEqual(data["auth_type"], "api_token")
        self.assertIn("token", data)
        self.assertEqual(data["token"]["name"], "Test Token")
        self.assertIn("permissions", data["token"])
        self.assertIn("created", data["token"])

    def test_only_get_allowed(self):
        self.client.login(username="testuser", password="testpassword")
        for method in ["post", "put", "patch", "delete"]:
            res = getattr(self.client, method)("/api/me/")
            self.assertEqual(
                res.status_code, 405, f"{method.upper()} should not be allowed"
            )
