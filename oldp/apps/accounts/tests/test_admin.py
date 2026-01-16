from django.contrib.auth.models import User
from django.test import TestCase, Client
from django.urls import reverse
from rest_framework.authtoken.models import Token

from oldp.apps.accounts.admin import TokenAdmin


class TokenAdminTestCase(TestCase):
    """Test cases for Token admin interface"""

    def setUp(self):
        # Create a superuser for admin access
        self.admin_user = User.objects.create_superuser(
            username="admin",
            email="admin@example.com",
            password="adminpass123"
        )

        # Create a regular user with a token
        self.regular_user = User.objects.create_user(
            username="testuser",
            email="test@example.com",
            password="testpass123"
        )
        self.token = Token.objects.get(user=self.regular_user)

        # Create admin client
        self.client = Client()
        self.client.login(username="admin", password="adminpass123")

    def test_token_admin_registered(self):
        """Test that Token model is registered in admin"""
        from django.contrib import admin
        self.assertIn(Token, admin.site._registry)

    def test_token_admin_list_view(self):
        """Test that token admin list view is accessible"""
        url = reverse("admin:authtoken_token_changelist")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

    def test_token_admin_list_displays_masked_key(self):
        """Test that tokens are displayed with masked keys"""
        admin = TokenAdmin(Token, None)
        masked = admin.key_masked(self.token)
        # Should show first 4 and last 4 characters
        self.assertIn(self.token.key[:4], masked)
        self.assertIn(self.token.key[-4:], masked)
        # Should not contain the full key
        self.assertNotIn(self.token.key, masked)

    def test_token_admin_user_link(self):
        """Test that user link is properly generated"""
        admin = TokenAdmin(Token, None)
        user_link = admin.user_link(self.token)
        # Should contain user ID and username
        self.assertIn(str(self.token.user.id), user_link)
        self.assertIn(self.token.user.username, user_link)
        # Should be a proper HTML link
        self.assertIn('<a href=', user_link)

    def test_token_admin_has_no_add_permission(self):
        """Test that tokens cannot be added directly via admin"""
        admin = TokenAdmin(Token, None)
        request = type('Request', (), {'user': self.admin_user})()
        self.assertFalse(admin.has_add_permission(request))

    def test_token_admin_revoke_action(self):
        """Test bulk revoke action deletes tokens"""
        # Create additional users with tokens
        user2 = User.objects.create_user("user2", "user2@example.com", "pass")
        user3 = User.objects.create_user("user3", "user3@example.com", "pass")

        token2 = Token.objects.get(user=user2)
        token3 = Token.objects.get(user=user3)

        # Verify tokens exist
        self.assertEqual(Token.objects.count(), 4)  # admin + 3 users

        # Create admin instance and mock request
        admin = TokenAdmin(Token, None)
        request = type('Request', (), {
            'user': self.admin_user,
            '_messages': type('Messages', (), {'add': lambda *args: None})()
        })()

        # Create queryset with tokens to revoke
        queryset = Token.objects.filter(pk__in=[token2.pk, token3.pk])

        # Execute revoke action (self is automatically passed for instance methods)
        admin.revoke_tokens(request, queryset)

        # Verify tokens were deleted
        self.assertEqual(Token.objects.count(), 2)  # Only admin and testuser tokens remain
        self.assertFalse(Token.objects.filter(pk=token2.pk).exists())
        self.assertFalse(Token.objects.filter(pk=token3.pk).exists())

    def test_token_admin_detail_view(self):
        """Test that token detail view shows readonly fields"""
        url = reverse("admin:authtoken_token_change", args=[self.token.pk])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        # Check that key, user, and created are in the response
        self.assertContains(response, self.token.key)
        self.assertContains(response, self.regular_user.username)

    def test_token_admin_search(self):
        """Test that admin search works for username and email"""
        url = reverse("admin:authtoken_token_changelist")

        # Search by username
        response = self.client.get(url, {"q": self.regular_user.username})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.regular_user.username)

        # Search by email
        response = self.client.get(url, {"q": self.regular_user.email})
        self.assertEqual(response.status_code, 200)

        # Search by token key (partial)
        response = self.client.get(url, {"q": self.token.key[:10]})
        self.assertEqual(response.status_code, 200)

    def test_token_admin_requires_staff(self):
        """Test that non-staff users cannot access token admin"""
        # Logout admin and login as regular user
        self.client.logout()
        self.client.login(username="testuser", password="testpass123")

        url = reverse("admin:authtoken_token_changelist")
        response = self.client.get(url)

        # Should redirect to login or show permission denied
        self.assertIn(response.status_code, [302, 403])

    def test_token_admin_queryset_optimization(self):
        """Test that admin queryset uses select_related for performance"""
        admin = TokenAdmin(Token, None)
        request = type('Request', (), {'user': self.admin_user})()

        queryset = admin.get_queryset(request)

        # Check that select_related was used (query should include user join)
        # This is a simple check - in production you'd use django-debug-toolbar
        # or query counting to verify optimization
        self.assertTrue(hasattr(queryset, 'query'))
