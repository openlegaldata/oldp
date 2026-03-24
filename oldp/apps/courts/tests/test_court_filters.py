"""Tests for court API filtering and search."""

from django.test import override_settings
from rest_framework import status
from rest_framework.test import APIClient, APITestCase

from oldp.apps.courts.models import Court, State


@override_settings(
    CACHES={"default": {"BACKEND": "django.core.cache.backends.dummy.DummyCache"}}
)
class CourtAPIFilterTestCase(APITestCase):
    """Tests that court API filters work correctly."""

    fixtures = [
        "locations/countries.json",
        "locations/states.json",
        "locations/cities.json",
        "courts/courts.json",
    ]

    def setUp(self):
        self.client = APIClient()
        # Ensure we have courts with known names from fixtures
        self.all_count = Court.objects.filter(review_status="accepted").count()
        self.assertTrue(self.all_count > 0, "Fixtures must contain courts")

    def test_unfiltered_returns_all(self):
        """Without filters, all accepted courts are returned."""
        response = self.client.get("/api/courts/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], self.all_count)

    def test_filter_name_icontains(self):
        """name filter should match courts by partial name (case-insensitive)."""
        # Pick a court and search for part of its name
        court = Court.objects.filter(review_status="accepted").first()
        partial = court.name[:5]

        response = self.client.get(f"/api/courts/?name={partial}")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertGreater(response.data["count"], 0)
        # Every returned court's name should contain the partial
        for item in response.data["results"]:
            self.assertIn(partial.lower(), item["name"].lower())

    def test_filter_name_returns_fewer_results(self):
        """Filtering by name should return fewer results than unfiltered."""
        # Use a specific-enough name fragment
        court = Court.objects.filter(review_status="accepted").first()
        response = self.client.get(f"/api/courts/?name={court.name}")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertLess(response.data["count"], self.all_count)

    def test_filter_slug_exact(self):
        """slug filter should match exact slug."""
        court = Court.objects.filter(review_status="accepted").first()
        response = self.client.get(f"/api/courts/?slug={court.slug}")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["slug"], court.slug)

    def test_filter_code_exact(self):
        """code filter should match exact code."""
        court = Court.objects.filter(review_status="accepted").first()
        response = self.client.get(f"/api/courts/?code={court.code}")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertGreater(response.data["count"], 0)
        for item in response.data["results"]:
            self.assertEqual(item["code"], court.code)

    def test_filter_court_type(self):
        """court_type filter should filter by type."""
        court = Court.objects.filter(
            review_status="accepted", court_type__isnull=False
        ).first()
        if not court:
            self.skipTest("No courts with court_type in fixtures")
        response = self.client.get(f"/api/courts/?court_type={court.court_type}")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertGreater(response.data["count"], 0)

    def test_filter_aliases_icontains(self):
        """aliases filter should match courts by partial alias text."""
        court = Court.objects.filter(
            review_status="accepted", aliases__isnull=False
        ).exclude(aliases="").first()
        if not court:
            # Create a court with aliases for this test
            state = State.objects.first()
            court = Court.objects.create(
                name="Test Gericht Frankfurt",
                code="TGFFM",
                slug="test-gericht-frankfurt",
                state=state,
                aliases="Frankfurter Gericht\nFG Frankfurt",
                review_status="accepted",
            )

        # Search by partial alias
        alias_part = court.aliases.split("\n")[0][:8]
        response = self.client.get(f"/api/courts/?aliases={alias_part}")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertGreater(response.data["count"], 0)

    def test_search_parameter(self):
        """search= parameter should search across name, aliases, code."""
        court = Court.objects.filter(review_status="accepted").first()
        # Search by code
        response = self.client.get(f"/api/courts/?search={court.code}")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertGreater(response.data["count"], 0)

    def test_search_returns_filtered_results(self):
        """search= should not return unfiltered results."""
        response = self.client.get("/api/courts/?search=NONEXISTENTXYZ123")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 0)

    def test_nonexistent_name_returns_empty(self):
        """Searching for a non-existent name returns empty results."""
        response = self.client.get("/api/courts/?name=ZZZZNOTACOURT")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 0)
