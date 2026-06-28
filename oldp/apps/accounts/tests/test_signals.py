from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework.authtoken.models import Token

from oldp.apps.accounts.models import UserProfile


class AccountsSignalsTestCase(TestCase):
    def test_token_create(self):
        """Tests if an API token is correctly created on save signal"""
        user = User.objects.create_user(
            username="foo", email="foo@bar.com", password="foooooo"
        )
        token = Token.objects.get(user=user)

        self.assertEqual(token.user, user, "User does not match")

    def test_profile_create(self):
        """A UserProfile is created automatically when a user is created."""
        user = User.objects.create_user(
            username="profileuser", email="profile@bar.com", password="foooooo"
        )
        self.assertTrue(
            UserProfile.objects.filter(user=user).exists(),
            "Profile was not created on user creation",
        )
        self.assertEqual(user.profile.user, user)

    def test_profile_create_is_idempotent(self):
        """Re-saving an existing user does not create a duplicate profile."""
        user = User.objects.create_user(
            username="resave", email="resave@bar.com", password="foooooo"
        )
        user.first_name = "Changed"
        user.save()
        self.assertEqual(UserProfile.objects.filter(user=user).count(), 1)
