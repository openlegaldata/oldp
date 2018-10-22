from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework.authtoken.models import Token


class AccountsSignalsTestCase(TestCase):
    def test_token_create(self):
        """Tests if an API token is correctly created on save signal"""
        user = User.objects.create_user(username='foo', email='foo@bar.com', password='foooooo')
        token = Token.objects.get(user=user)

        self.assertEqual(token.user, user, 'User does not match')
