from datetime import timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone

from oldp.apps.accounts.models import APIToken


class APITokenModelTestCase(TestCase):
    """Test cases for APIToken model"""

    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass123"
        )

    def test_token_creation(self):
        """Test that a token is created with auto-generated key"""
        token = APIToken.objects.create(user=self.user, name="Test Token")

        self.assertIsNotNone(token.key)
        self.assertEqual(len(token.key), 40)
        self.assertEqual(token.name, "Test Token")
        self.assertTrue(token.is_active)
        self.assertIsNone(token.last_used)
        self.assertIsNone(token.expires_at)

    def test_token_key_is_unique(self):
        """Test that token keys are unique"""
        token1 = APIToken.objects.create(user=self.user, name="Token 1")
        token2 = APIToken.objects.create(user=self.user, name="Token 2")

        self.assertNotEqual(token1.key, token2.key)

    def test_multiple_tokens_per_user(self):
        """Test that a user can have multiple tokens"""
        APIToken.objects.create(user=self.user, name="Token 1")
        APIToken.objects.create(user=self.user, name="Token 2")
        APIToken.objects.create(user=self.user, name="Token 3")

        user_tokens = APIToken.objects.filter(user=self.user)
        self.assertEqual(user_tokens.count(), 3)

    def test_token_string_representation(self):
        """Test token __str__ method"""
        token = APIToken.objects.create(user=self.user, name="My Token")
        expected = f"{self.user.username} - My Token"
        self.assertEqual(str(token), expected)

    def test_is_expired_with_no_expiration(self):
        """Test that tokens with no expiration never expire"""
        token = APIToken.objects.create(user=self.user, name="Token")
        self.assertFalse(token.is_expired())

    def test_is_expired_with_future_expiration(self):
        """Test that tokens with future expiration are not expired"""
        future = timezone.now() + timedelta(days=30)
        token = APIToken.objects.create(user=self.user, name="Token", expires_at=future)
        self.assertFalse(token.is_expired())

    def test_is_expired_with_past_expiration(self):
        """Test that tokens with past expiration are expired"""
        past = timezone.now() - timedelta(days=1)
        token = APIToken.objects.create(user=self.user, name="Token", expires_at=past)
        self.assertTrue(token.is_expired())

    def test_is_valid_active_not_expired(self):
        """Test that active, non-expired tokens are valid"""
        token = APIToken.objects.create(user=self.user, name="Token")
        self.assertTrue(token.is_valid())

    def test_is_valid_inactive(self):
        """Test that inactive tokens are not valid"""
        token = APIToken.objects.create(user=self.user, name="Token", is_active=False)
        self.assertFalse(token.is_valid())

    def test_is_valid_expired(self):
        """Test that expired tokens are not valid"""
        past = timezone.now() - timedelta(days=1)
        token = APIToken.objects.create(user=self.user, name="Token", expires_at=past)
        self.assertFalse(token.is_valid())

    def test_has_scope_no_scopes(self):
        """Test that tokens with no scopes have full access"""
        token = APIToken.objects.create(user=self.user, name="Token")
        self.assertTrue(token.has_scope("read"))
        self.assertTrue(token.has_scope("write"))
        self.assertTrue(token.has_scope("admin"))

    def test_has_scope_with_scopes(self):
        """Test that tokens with scopes only have specified access"""
        token = APIToken.objects.create(
            user=self.user, name="Token", scopes=["read", "write"]
        )
        self.assertTrue(token.has_scope("read"))
        self.assertTrue(token.has_scope("write"))
        self.assertFalse(token.has_scope("admin"))

    def test_mark_used_updates_last_used(self):
        """Test that mark_used updates the last_used timestamp"""
        token = APIToken.objects.create(user=self.user, name="Token")
        self.assertIsNone(token.last_used)

        # Mark as used
        token.mark_used()

        # Refresh from database
        token.refresh_from_db()
        self.assertIsNotNone(token.last_used)

        # Check that it's recent (within last 5 seconds)
        time_diff = timezone.now() - token.last_used
        self.assertLess(time_diff.total_seconds(), 5)

    def test_generate_key_creates_unique_keys(self):
        """Test that generate_key creates unique keys"""
        key1 = APIToken.generate_key()
        key2 = APIToken.generate_key()

        self.assertNotEqual(key1, key2)
        self.assertEqual(len(key1), 40)
        self.assertEqual(len(key2), 40)

    def test_token_ordering(self):
        """Test that tokens are ordered by creation date (newest first)"""
        token1 = APIToken.objects.create(user=self.user, name="Token 1")
        token2 = APIToken.objects.create(user=self.user, name="Token 2")
        token3 = APIToken.objects.create(user=self.user, name="Token 3")

        tokens = list(APIToken.objects.all())
        self.assertEqual(tokens[0], token3)
        self.assertEqual(tokens[1], token2)
        self.assertEqual(tokens[2], token1)

    def test_token_deletion_on_user_deletion(self):
        """Test that tokens are deleted when user is deleted"""
        token = APIToken.objects.create(user=self.user, name="Token")
        token_id = token.id

        self.user.delete()

        self.assertFalse(APIToken.objects.filter(id=token_id).exists())
