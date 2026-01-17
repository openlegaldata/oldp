"""
Tests for the case creation admin dashboard.
"""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

User = get_user_model()


class CaseCreationDashboardTestCase(TestCase):
    """Tests for the case creation dashboard view."""

    def setUp(self):
        # Create a staff user
        self.staff_user = User.objects.create_user(
            username="staffuser",
            email="staff@example.com",
            password="testpass123",
            is_staff=True,
        )
        # Create a regular user
        self.regular_user = User.objects.create_user(
            username="regularuser",
            email="regular@example.com",
            password="testpass123",
            is_staff=False,
        )

    def test_dashboard_requires_staff(self):
        """Test that non-staff users cannot access the dashboard."""
        self.client.login(username="regularuser", password="testpass123")
        response = self.client.get(reverse("cases_creation_dashboard"))
        # Should redirect to login
        self.assertNotEqual(response.status_code, 200)

    def test_dashboard_accessible_by_staff(self):
        """Test that staff users can access the dashboard."""
        self.client.login(username="staffuser", password="testpass123")
        response = self.client.get(reverse("cases_creation_dashboard"))
        self.assertEqual(response.status_code, 200)

    def test_dashboard_default_days(self):
        """Test dashboard uses default 30 days."""
        self.client.login(username="staffuser", password="testpass123")
        response = self.client.get(reverse("cases_creation_dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["days"], 30)

    def test_dashboard_custom_days(self):
        """Test dashboard accepts custom days parameter."""
        self.client.login(username="staffuser", password="testpass123")
        response = self.client.get(reverse("cases_creation_dashboard") + "?days=7")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["days"], 7)

    def test_dashboard_days_validation(self):
        """Test dashboard validates days parameter."""
        self.client.login(username="staffuser", password="testpass123")

        # Test minimum bound
        response = self.client.get(reverse("cases_creation_dashboard") + "?days=0")
        self.assertEqual(response.context["days"], 1)

        # Test maximum bound
        response = self.client.get(reverse("cases_creation_dashboard") + "?days=1000")
        self.assertEqual(response.context["days"], 365)

    def test_dashboard_contains_required_context(self):
        """Test dashboard context contains required data."""
        self.client.login(username="staffuser", password="testpass123")
        response = self.client.get(reverse("cases_creation_dashboard"))

        self.assertIn("cases_per_day", response.context)
        self.assertIn("cases_per_token", response.context)
        self.assertIn("total_cases", response.context)
        self.assertIn("api_created", response.context)
        self.assertIn("pending_approval", response.context)
