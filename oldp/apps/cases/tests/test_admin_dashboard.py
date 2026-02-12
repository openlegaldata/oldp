"""Tests for the case creation admin dashboard."""

from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from oldp.apps.accounts.models import APIToken
from oldp.apps.cases.models import Case
from oldp.apps.courts.models import Court

User = get_user_model()


class CaseCreationDashboardTestCase(TestCase):
    """Tests for the case creation dashboard view."""

    fixtures = [
        "locations/countries.json",
        "locations/states.json",
        "locations/cities.json",
        "courts/courts.json",
    ]

    def setUp(self):
        self.staff_user = User.objects.create_user(
            username="staffuser",
            email="staff@example.com",
            password="testpass123",
            is_staff=True,
        )
        self.regular_user = User.objects.create_user(
            username="regularuser",
            email="regular@example.com",
            password="testpass123",
            is_staff=False,
        )
        self.url = reverse("cases_creation_dashboard")

    def _create_case(self, slug, days_ago=0, token=None, review_status="accepted"):
        """Helper to create a case with a specific created_date offset."""
        case = Case.objects.create(
            slug=slug,
            content="<p>Test</p>",
            court_id=Court.DEFAULT_ID,
            created_by_token=token,
            review_status=review_status,
        )
        if days_ago:
            target_date = timezone.now() - timedelta(days=days_ago)
            Case.objects.filter(pk=case.pk).update(created_date=target_date)
            case.refresh_from_db()
        return case

    def test_dashboard_requires_staff(self):
        """Test that non-staff users cannot access the dashboard."""
        self.client.login(username="regularuser", password="testpass123")
        response = self.client.get(self.url)
        self.assertNotEqual(response.status_code, 200)

    def test_dashboard_accessible_by_staff(self):
        """Test that staff users can access the dashboard."""
        self.client.login(username="staffuser", password="testpass123")
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)

    def test_dashboard_default_date_range(self):
        """Test dashboard uses default 30-day range."""
        self.client.login(username="staffuser", password="testpass123")
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["end_date"], date.today())
        self.assertEqual(
            response.context["start_date"],
            date.today() - timedelta(days=29),
        )

    def test_dashboard_date_range_params(self):
        """Test dashboard accepts explicit start_date and end_date."""
        self.client.login(username="staffuser", password="testpass123")
        response = self.client.get(
            self.url + "?start_date=2025-01-01&end_date=2025-01-31"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["start_date"], date(2025, 1, 1))
        self.assertEqual(response.context["end_date"], date(2025, 1, 31))

    def test_dashboard_days_shortcut_still_works(self):
        """Test backward compatibility with days parameter."""
        self.client.login(username="staffuser", password="testpass123")
        response = self.client.get(self.url + "?days=7")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["end_date"], date.today())
        self.assertEqual(
            response.context["start_date"],
            date.today() - timedelta(days=6),
        )

    def test_dashboard_invalid_dates_fallback(self):
        """Test that invalid dates fall back to defaults."""
        self.client.login(username="staffuser", password="testpass123")
        response = self.client.get(
            self.url + "?start_date=not-a-date&end_date=also-bad"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["end_date"], date.today())
        self.assertEqual(
            response.context["start_date"],
            date.today() - timedelta(days=29),
        )

    def test_dashboard_days_validation(self):
        """Test dashboard validates days parameter bounds."""
        self.client.login(username="staffuser", password="testpass123")

        # Minimum bound
        response = self.client.get(self.url + "?days=0")
        expected_start = date.today()
        self.assertEqual(response.context["start_date"], expected_start)

        # Maximum bound
        response = self.client.get(self.url + "?days=1000")
        expected_start = date.today() - timedelta(days=364)
        self.assertEqual(response.context["start_date"], expected_start)

    def test_dashboard_contains_required_context(self):
        """Test dashboard context contains required data."""
        self.client.login(username="staffuser", password="testpass123")
        response = self.client.get(self.url)

        self.assertIn("items_per_day", response.context)
        self.assertIn("items_per_token", response.context)
        self.assertIn("total_items", response.context)
        self.assertIn("api_created", response.context)
        self.assertIn("pending_approval", response.context)
        self.assertIn("start_date", response.context)
        self.assertIn("end_date", response.context)
        self.assertIn("selected_token", response.context)
        self.assertIn("token_choices", response.context)
        self.assertIn("processing_steps", response.context)

    def test_dashboard_token_filter_none(self):
        """Test filtering for non-API cases (no token)."""
        self.client.login(username="staffuser", password="testpass123")
        token = APIToken.objects.create(user=self.staff_user, name="Test Token")
        self._create_case("case-with-token", token=token)
        self._create_case("case-without-token")

        response = self.client.get(self.url + "?token=none")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["total_items"], 1)
        self.assertEqual(response.context["selected_token"], "none")

    def test_dashboard_token_filter_specific(self):
        """Test filtering for a specific API token."""
        self.client.login(username="staffuser", password="testpass123")
        token1 = APIToken.objects.create(user=self.staff_user, name="Token 1")
        token2 = APIToken.objects.create(user=self.staff_user, name="Token 2")
        self._create_case("case-token1", token=token1)
        self._create_case("case-token2", token=token2)

        response = self.client.get(self.url + f"?token={token1.pk}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["total_items"], 1)
        # token_choices should still show both tokens (computed before filter)
        self.assertEqual(len(response.context["token_choices"]), 2)

    def test_dashboard_batch_processing_post(self):
        """Test batch processing changes case review status."""
        self.client.login(username="staffuser", password="testpass123")
        case = self._create_case("batch-test-case", review_status="accepted")

        today_str = date.today().strftime("%Y-%m-%d")
        response = self.client.post(
            self.url,
            {
                "selected_dates": [today_str],
                "processing_step": "set_review_pending",
                "token": "",
            },
        )
        self.assertEqual(response.status_code, 302)

        case.refresh_from_db()
        self.assertEqual(case.review_status, "pending")

    def test_dashboard_batch_processing_no_dates(self):
        """Test that POST with no dates shows error."""
        self.client.login(username="staffuser", password="testpass123")
        response = self.client.post(
            self.url,
            {
                "processing_step": "set_review_pending",
                "token": "",
            },
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        messages_list = list(response.context["messages"])
        self.assertTrue(any("No dates selected" in str(m) for m in messages_list))

    def test_dashboard_batch_processing_no_step(self):
        """Test that POST with no processing step shows error."""
        self.client.login(username="staffuser", password="testpass123")
        today_str = date.today().strftime("%Y-%m-%d")
        response = self.client.post(
            self.url,
            {
                "selected_dates": [today_str],
                "processing_step": "",
                "token": "",
            },
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        messages_list = list(response.context["messages"])
        self.assertTrue(any("No processing step" in str(m) for m in messages_list))

    def test_dashboard_post_requires_staff(self):
        """Test that non-staff users cannot POST to the dashboard."""
        self.client.login(username="regularuser", password="testpass123")
        response = self.client.post(
            self.url,
            {
                "selected_dates": [date.today().strftime("%Y-%m-%d")],
                "processing_step": "set_review_pending",
                "token": "",
            },
        )
        # Should redirect to login page, not process the request
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login", response.url)
