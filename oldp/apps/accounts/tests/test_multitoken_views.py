from datetime import timedelta

from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from oldp.apps.accounts.models import APIToken


class MultiTokenViewsTestCase(TestCase):
    """Test cases for multi-token system views"""

    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass123"
        )
        self.client = Client()
        self.client.login(username="testuser", password="testpass123")

    def test_token_list_view(self):
        """Test that token list view displays user's tokens"""
        # Create some tokens
        token1 = APIToken.objects.create(user=self.user, name="Token 1")
        token2 = APIToken.objects.create(user=self.user, name="Token 2")

        # Create a token for another user (shouldn't appear)
        other_user = User.objects.create_user("other", "other@example.com", "pass")
        other_token = APIToken.objects.create(user=other_user, name="Other Token")

        url = reverse("account_api_tokens")
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertIn("tokens", response.context)

        # Check that only this user's tokens are shown
        tokens_in_context = list(response.context["tokens"])
        self.assertEqual(len(tokens_in_context), 2)
        self.assertIn(token1, tokens_in_context)
        self.assertIn(token2, tokens_in_context)
        self.assertNotIn(other_token, tokens_in_context)

    def test_token_list_view_requires_authentication(self):
        """Test that token list view requires authentication"""
        self.client.logout()
        url = reverse("account_api_tokens")
        response = self.client.get(url)

        # Should redirect to login
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response.url)

    def test_token_create_view_get(self):
        """Test that token create view displays creation form"""
        url = reverse("account_api_token_create")
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertIn("Create API Token", response.content.decode())

    def test_token_create_view_post_success(self):
        """Test creating a new token via POST"""
        url = reverse("account_api_token_create")
        data = {"name": "My New Token", "expiration_days": "365"}

        response = self.client.post(url, data)

        # Should redirect to token list
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("account_api_tokens"))

        # Verify token was created
        token = APIToken.objects.get(user=self.user, name="My New Token")
        self.assertIsNotNone(token)
        self.assertTrue(token.is_active)

        # Verify expiration is set (approximately 1 year from now)
        self.assertIsNotNone(token.expires_at)
        expected_expiration = timezone.now() + timedelta(days=365)
        time_diff = abs((token.expires_at - expected_expiration).total_seconds())
        self.assertLess(time_diff, 60)  # Within 1 minute

    def test_token_create_view_post_no_expiration(self):
        """Test creating a token with no expiration"""
        url = reverse("account_api_token_create")
        data = {"name": "Permanent Token", "expiration_days": "0"}

        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302)

        token = APIToken.objects.get(user=self.user, name="Permanent Token")
        self.assertIsNone(token.expires_at)

    def test_token_create_view_post_missing_name(self):
        """Test that token creation fails without a name"""
        url = reverse("account_api_token_create")
        data = {"name": "", "expiration_days": "365"}

        initial_count = APIToken.objects.count()
        response = self.client.post(url, data)

        # Should redirect back to list with error message
        self.assertEqual(response.status_code, 302)

        # No token should be created
        self.assertEqual(APIToken.objects.count(), initial_count)

    def test_token_create_view_requires_authentication(self):
        """Test that token creation requires authentication"""
        self.client.logout()
        url = reverse("account_api_token_create")
        response = self.client.post(url, {"name": "Token"})

        # Should redirect to login
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response.url)

    def test_token_revoke_view_get(self):
        """Test that revoke view displays confirmation page"""
        token = APIToken.objects.create(user=self.user, name="Token to Revoke")
        url = reverse("account_api_token_revoke", args=[token.id])
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertIn(token.name, response.content.decode())

    def test_token_revoke_view_post_success(self):
        """Test revoking a token via POST"""
        token = APIToken.objects.create(user=self.user, name="Token to Revoke")
        token_id = token.id

        url = reverse("account_api_token_revoke", args=[token_id])
        response = self.client.post(url)

        # Should redirect to token list
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("account_api_tokens"))

        # Verify token was deleted
        self.assertFalse(APIToken.objects.filter(id=token_id).exists())

    def test_token_revoke_view_wrong_user(self):
        """Test that users can only revoke their own tokens"""
        # Create another user with a token
        other_user = User.objects.create_user("other", "other@example.com", "pass")
        other_token = APIToken.objects.create(user=other_user, name="Other Token")

        # Try to revoke the other user's token
        url = reverse("account_api_token_revoke", args=[other_token.id])
        response = self.client.get(url)

        # Should return 404
        self.assertEqual(response.status_code, 404)

        # Verify token still exists
        self.assertTrue(APIToken.objects.filter(id=other_token.id).exists())

    def test_token_revoke_view_requires_authentication(self):
        """Test that token revocation requires authentication"""
        token = APIToken.objects.create(user=self.user, name="Token")

        self.client.logout()
        url = reverse("account_api_token_revoke", args=[token.id])
        response = self.client.post(url)

        # Should redirect to login
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response.url)

        # Token should still exist
        self.assertTrue(APIToken.objects.filter(id=token.id).exists())

    def test_token_list_shows_token_details(self):
        """Test that token list shows relevant token information"""
        future = timezone.now() + timedelta(days=30)

        APIToken.objects.create(
            user=self.user, name="Detailed Token", expires_at=future, is_active=True
        )

        url = reverse("account_api_tokens")
        response = self.client.get(url)

        content = response.content.decode()
        self.assertIn("Detailed Token", content)

    def test_token_ordering_in_list(self):
        """Test that tokens are ordered newest first"""
        token1 = APIToken.objects.create(user=self.user, name="Token 1")
        token2 = APIToken.objects.create(user=self.user, name="Token 2")
        token3 = APIToken.objects.create(user=self.user, name="Token 3")

        url = reverse("account_api_tokens")
        response = self.client.get(url)

        tokens = list(response.context["tokens"])
        self.assertEqual(tokens[0], token3)
        self.assertEqual(tokens[1], token2)
        self.assertEqual(tokens[2], token1)
