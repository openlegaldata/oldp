from django.contrib.auth.models import User
from django.test import LiveServerTestCase


class AccountsViewsTestCase(LiveServerTestCase):
    # fixtures = ['auth.json']  # Test user (login: test, pw: test)
    username = 'test'
    password = 'test'

    def setUp(self):
        self.user = User.objects.create_user(self.username, 'test@example.com', self.password)

    def test_profile_view(self):
        self.assertTrue(self.client.login(username=self.username, password=self.password), 'Login failed')

        res = self.client.get('/accounts/profile/')

        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.context['user'].is_authenticated)

    def test_api_view(self):
        self.assertTrue(self.client.login(username=self.username, password=self.password), 'Login failed')

        res = self.client.get('/accounts/api/')

        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.context['user'].is_authenticated)

    def test_api_renew_view(self):
        self.assertTrue(self.client.login(username=self.username, password=self.password), 'Login failed')

        res = self.client.get('/accounts/api/renew/')

        self.assertEqual(res.status_code, 302)
