from django.contrib.auth.models import User
from django.test import LiveServerTestCase
from rest_framework.authtoken.models import Token


class AccountsViewsTestCase(LiveServerTestCase):
    # fixtures = ['auth.json']  # Test user (login: test, pw: test)
    username = "test"
    password = "test"

    def setUp(self):
        self.user = User.objects.create_user(
            self.username, "test@example.com", self.password
        )

    def test_profile_view(self):
        self.assertTrue(
            self.client.login(username=self.username, password=self.password),
            "Login failed",
        )

        res = self.client.get("/accounts/profile/")

        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.context["user"].is_authenticated)

    def test_api_view(self):
        self.assertTrue(
            self.client.login(username=self.username, password=self.password),
            "Login failed",
        )

        res = self.client.get("/accounts/api/")

        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.context["user"].is_authenticated)

    def test_api_renew_view(self):
        self.assertTrue(
            self.client.login(username=self.username, password=self.password),
            "Login failed",
        )

        res = self.client.get("/accounts/api/renew/")

        self.assertEqual(res.status_code, 302)

    def test_api_renew_view_changes_token(self):
        """Test that renewing the token actually creates a new token"""
        self.assertTrue(
            self.client.login(username=self.username, password=self.password),
            "Login failed",
        )

        # Get the initial token
        initial_token = Token.objects.get(user=self.user)
        initial_key = initial_token.key

        # Renew the token
        res = self.client.get("/accounts/api/renew/")

        # Check redirect
        self.assertEqual(res.status_code, 302)
        self.assertEqual(res.url, "/accounts/api/")

        # Get the new token
        new_token = Token.objects.get(user=self.user)
        new_key = new_token.key

        # Verify the token has changed
        self.assertNotEqual(
            initial_key, new_key, "Token key should have changed after renewal"
        )

    def test_api_renew_view_invalidates_old_token(self):
        """Test that the old token is invalidated after renewal"""
        self.assertTrue(
            self.client.login(username=self.username, password=self.password),
            "Login failed",
        )

        # Get the initial token
        initial_token = Token.objects.get(user=self.user)
        initial_key = initial_token.key

        # Renew the token
        self.client.get("/accounts/api/renew/")

        # Verify the old token no longer exists
        old_token_exists = Token.objects.filter(key=initial_key).exists()
        self.assertFalse(
            old_token_exists, "Old token should not exist after renewal"
        )

    def test_api_renew_view_shows_success_message(self):
        """Test that a success message is shown after renewal"""
        self.assertTrue(
            self.client.login(username=self.username, password=self.password),
            "Login failed",
        )

        # Renew the token
        res = self.client.get("/accounts/api/renew/", follow=True)

        # Check for success message
        messages = list(res.context["messages"])
        self.assertEqual(len(messages), 1)
        self.assertEqual(str(messages[0]), "Your API access token has been renewed successfully.")

    def test_api_renew_view_requires_authentication(self):
        """Test that the API renew view requires authentication"""
        res = self.client.get("/accounts/api/renew/")

        # Should redirect to login
        self.assertEqual(res.status_code, 302)
        self.assertIn("/accounts/login/", res.url)
