from datetime import timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone
from rest_framework import exceptions

from oldp.apps.accounts.authentication import APITokenAuthentication
from oldp.apps.accounts.models import APIToken


class APITokenAuthenticationTestCase(TestCase):
    """Test cases for APITokenAuthentication backend"""

    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass123"
        )
        self.auth = APITokenAuthentication()

    def test_authenticate_valid_token(self):
        """Test authentication with a valid token"""
        token = APIToken.objects.create(user=self.user, name="Test Token")

        user, auth_token = self.auth.authenticate_credentials(token.key)

        self.assertEqual(user, self.user)
        self.assertEqual(auth_token, token)

    def test_authenticate_invalid_token(self):
        """Test that authentication fails with invalid token"""
        with self.assertRaises(exceptions.AuthenticationFailed) as context:
            self.auth.authenticate_credentials("invalid_token_key_1234567890123456")

        self.assertIn("Invalid token", str(context.exception))

    def test_authenticate_inactive_token(self):
        """Test that authentication fails with inactive token"""
        token = APIToken.objects.create(
            user=self.user, name="Inactive Token", is_active=False
        )

        with self.assertRaises(exceptions.AuthenticationFailed) as context:
            self.auth.authenticate_credentials(token.key)

        self.assertIn("inactive", str(context.exception).lower())

    def test_authenticate_expired_token(self):
        """Test that authentication fails with expired token"""
        past = timezone.now() - timedelta(days=1)
        token = APIToken.objects.create(
            user=self.user, name="Expired Token", expires_at=past
        )

        with self.assertRaises(exceptions.AuthenticationFailed) as context:
            self.auth.authenticate_credentials(token.key)

        self.assertIn("expired", str(context.exception).lower())

    def test_authenticate_inactive_user(self):
        """Test that authentication fails when user is inactive"""
        token = APIToken.objects.create(user=self.user, name="Token")

        # Deactivate the user
        self.user.is_active = False
        self.user.save()

        with self.assertRaises(exceptions.AuthenticationFailed) as context:
            self.auth.authenticate_credentials(token.key)

        self.assertIn("User inactive", str(context.exception))

    def test_authenticate_updates_last_used(self):
        """Test that successful authentication updates last_used timestamp"""
        token = APIToken.objects.create(user=self.user, name="Token")
        self.assertIsNone(token.last_used)

        # Authenticate
        self.auth.authenticate_credentials(token.key)

        # Refresh token from database
        token.refresh_from_db()

        # Verify last_used was updated
        self.assertIsNotNone(token.last_used)
        time_diff = timezone.now() - token.last_used
        self.assertLess(time_diff.total_seconds(), 5)

    def test_authenticate_valid_token_not_expired(self):
        """Test authentication with valid token that has future expiration"""
        future = timezone.now() + timedelta(days=30)
        token = APIToken.objects.create(
            user=self.user, name="Future Token", expires_at=future
        )

        user, auth_token = self.auth.authenticate_credentials(token.key)

        self.assertEqual(user, self.user)
        self.assertEqual(auth_token, token)

    def test_authenticate_with_scopes(self):
        """Test that authentication works with scoped tokens"""
        token = APIToken.objects.create(
            user=self.user, name="Scoped Token", scopes=["read", "write"]
        )

        user, auth_token = self.auth.authenticate_credentials(token.key)

        self.assertEqual(user, self.user)
        self.assertEqual(auth_token, token)
        self.assertTrue(auth_token.has_scope("read"))
        self.assertTrue(auth_token.has_scope("write"))
        self.assertFalse(auth_token.has_scope("admin"))

    def test_authentication_model(self):
        """Test that authentication uses correct model"""
        self.assertEqual(self.auth.model, APIToken)

    def test_authentication_keyword(self):
        """Test that authentication uses correct keyword"""
        self.assertEqual(self.auth.keyword, "Token")
