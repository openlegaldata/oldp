"""Tests for slug-based filtering across API endpoints.

Verifies that API endpoints which accept ID-based filtering also support
filtering by slug where the target model has a slug field.
"""

from django.contrib.auth.models import User
from django.test import override_settings
from rest_framework import status
from rest_framework.test import APIClient, APITestCase

from oldp.apps.cases.models import Case
from oldp.apps.courts.models import City, Court, State


@override_settings(
    CACHES={"default": {"BACKEND": "django.core.cache.backends.dummy.DummyCache"}},
    STORAGES={
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"
        },
    },
)
class CaseAPISlugFilterTestCase(APITestCase):
    """Tests for slug filters on the cases API."""

    fixtures = [
        "locations/countries.json",
        "locations/states.json",
        "locations/cities.json",
        "courts/courts.json",
    ]

    def setUp(self):
        self.client = APIClient()

        # Create a case so we have data to filter
        self.court = Court.objects.exclude(pk=Court.DEFAULT_ID).first()
        self.case = Case.objects.create(
            court=self.court,
            file_number="SLUG-TEST/01",
            date="2025-01-01",
            content="<p>Test case</p>",
            review_status="accepted",
        )

    def test_filter_court_state_slug(self):
        """court__state__slug filter returns cases from that state."""
        state = self.court.state
        response = self.client.get("/api/cases/", {"court__state__slug": state.slug})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertGreater(response.data["count"], 0)

    def test_filter_court_state_slug_matches_id(self):
        """court__state__slug and court__state return same results."""
        state = self.court.state
        response_id = self.client.get("/api/cases/", {"court__state": state.pk})
        response_slug = self.client.get(
            "/api/cases/", {"court__state__slug": state.slug}
        )
        self.assertEqual(response_id.status_code, status.HTTP_200_OK)
        self.assertEqual(response_slug.status_code, status.HTTP_200_OK)
        self.assertEqual(response_id.data["count"], response_slug.data["count"])

    def test_filter_court_state_slug_nonexistent(self):
        """Nonexistent court__state__slug returns empty results."""
        response = self.client.get("/api/cases/", {"court__state__slug": "nonexistent"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 0)


@override_settings(
    CACHES={"default": {"BACKEND": "django.core.cache.backends.dummy.DummyCache"}},
)
class CityAPISlugFilterTestCase(APITestCase):
    """Tests for slug filters on the cities API."""

    fixtures = [
        "locations/countries.json",
        "locations/states.json",
        "locations/cities.json",
    ]

    def test_filter_state_slug(self):
        """state__slug filter returns cities from that state."""
        state = State.objects.first()
        expected = City.objects.filter(state=state).count()
        if expected == 0:
            self.skipTest("No cities in this state")
        response = self.client.get(f"/api/cities/?state__slug={state.slug}")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], expected)

    def test_filter_state_slug_matches_id(self):
        """state__slug and state_id return same results."""
        state = State.objects.first()
        response_id = self.client.get(f"/api/cities/?state_id={state.pk}")
        response_slug = self.client.get(f"/api/cities/?state__slug={state.slug}")
        self.assertEqual(response_id.status_code, status.HTTP_200_OK)
        self.assertEqual(response_slug.status_code, status.HTTP_200_OK)
        self.assertEqual(response_id.data["count"], response_slug.data["count"])


@override_settings(
    CACHES={"default": {"BACKEND": "django.core.cache.backends.dummy.DummyCache"}},
    STORAGES={
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"
        },
    },
)
class LawAPISlugFilterTestCase(APITestCase):
    """Tests for slug filters on the laws API."""

    fixtures = [
        "locations/countries.json",
        "locations/states.json",
        "locations/cities.json",
        "courts/courts.json",
        "laws/laws.json",
    ]

    def setUp(self):
        self.client = APIClient()

    def test_filter_book_slug(self):
        """book__slug filter returns laws from books with that slug."""
        from oldp.apps.laws.models import Law, LawBook

        book = LawBook.objects.first()
        if not book:
            self.skipTest("No law books in fixtures")
        # book__slug matches all books with the same slug (multiple revisions)
        expected = Law.objects.filter(book__slug=book.slug).count()
        response = self.client.get(f"/api/laws/?book__slug={book.slug}")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], expected)

    def test_filter_book_slug_returns_subset(self):
        """book__slug filter returns a subset when combined with book__latest."""
        from oldp.apps.laws.models import Law, LawBook

        book = LawBook.objects.filter(latest=True).first()
        if not book:
            self.skipTest("No latest law books in fixtures")
        expected = Law.objects.filter(book__slug=book.slug, book__latest=True).count()
        response = self.client.get(
            f"/api/laws/?book__slug={book.slug}&book__latest=true"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], expected)


@override_settings(
    CACHES={"default": {"BACKEND": "django.core.cache.backends.dummy.DummyCache"}},
)
class AnnotationAPISlugFilterTestCase(APITestCase):
    """Tests for slug filters on the case annotations API."""

    fixtures = [
        "users/with_password_unittest.json",
        "locations/countries.json",
        "locations/states.json",
        "locations/cities.json",
        "courts/courts.json",
        "cases/cases.json",
        "annotations/labels.json",
    ]

    def setUp(self):
        self.admin = User.objects.get(pk=1)
        self.client = APIClient()
        self.client.force_authenticate(user=self.admin)

    def test_filter_label_slug(self):
        """label__slug filter on annotation labels works."""
        from oldp.apps.annotations.models import AnnotationLabel

        label = AnnotationLabel.objects.first()
        if not label:
            self.skipTest("No annotation labels in fixtures")
        response = self.client.get(f"/api/annotation_labels/?slug={label.slug}")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertGreater(response.data["count"], 0)
