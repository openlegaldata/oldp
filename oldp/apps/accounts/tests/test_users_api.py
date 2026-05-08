from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework.test import APIClient


class UsersApiPermissionTestCase(TestCase):
    """Tests that /api/users/ list and detail are restricted to staff users."""

    def setUp(self):
        self.staff = User.objects.create_user(
            "staffuser", "staff@example.com", "staffpass", is_staff=True
        )
        self.regular = User.objects.create_user(
            "regularuser", "regular@example.com", "regularpass"
        )
        self.client = APIClient()

    def test_list_anonymous_returns_401(self):
        res = self.client.get("/api/users/")
        self.assertEqual(res.status_code, 401)

    def test_detail_anonymous_returns_401(self):
        res = self.client.get(f"/api/users/{self.staff.pk}/")
        self.assertEqual(res.status_code, 401)

    def test_list_regular_user_returns_403(self):
        self.client.login(username="regularuser", password="regularpass")
        res = self.client.get("/api/users/")
        self.assertEqual(res.status_code, 403)

    def test_detail_regular_user_returns_403(self):
        self.client.login(username="regularuser", password="regularpass")
        res = self.client.get(f"/api/users/{self.staff.pk}/")
        self.assertEqual(res.status_code, 403)

    def test_list_staff_user_returns_200(self):
        self.client.login(username="staffuser", password="staffpass")
        res = self.client.get("/api/users/")
        self.assertEqual(res.status_code, 200)
        usernames = {u["username"] for u in res.json()["results"]}
        self.assertIn("staffuser", usernames)
        self.assertIn("regularuser", usernames)

    def test_detail_staff_user_returns_200(self):
        self.client.login(username="staffuser", password="staffpass")
        res = self.client.get(f"/api/users/{self.regular.pk}/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["username"], "regularuser")

    def test_me_action_accessible_to_regular_user(self):
        self.client.login(username="regularuser", password="regularpass")
        res = self.client.get("/api/users/me/")
        self.assertEqual(res.status_code, 200)
        usernames = {u["username"] for u in res.json()["results"]}
        self.assertEqual(usernames, {"regularuser"})
