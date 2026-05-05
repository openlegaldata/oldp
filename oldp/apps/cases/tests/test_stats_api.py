"""Tests for the case statistics API sub-endpoints.

Tests cover:
- Response structure (total, per-item buckets and totals)
- Default date range (last year) and bucket (month)
- Review status visibility (staff vs non-staff)
- Date range filtering
- Time bucket formatting (year/month/day)
- Grouping by country, state, court, source
- by_court requires court__state filter
- Filter by court, state, source
- Invalid parameter handling
"""

import datetime

from dateutil.relativedelta import relativedelta
from django.contrib.auth.models import User
from django.test import override_settings
from rest_framework import status
from rest_framework.test import APIClient, APITestCase

from oldp.apps.accounts.models import (
    APIToken,
    APITokenPermission,
    APITokenPermissionGroup,
)
from oldp.apps.cases.models import Case
from oldp.apps.courts.models import Court
from oldp.apps.sources.models import Source


@override_settings(
    CACHES={"default": {"BACKEND": "django.core.cache.backends.dummy.DummyCache"}},
    STORAGES={
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"
        },
    },
)
class CaseStatsAPITestCase(APITestCase):
    """Tests for GET /api/cases/stats/<dimension>/ endpoints."""

    fixtures = [
        "locations/countries.json",
        "locations/states.json",
        "locations/cities.json",
        "courts/courts.json",
    ]

    def setUp(self):
        # Staff user + token
        self.staff_user = User.objects.create_user(
            username="staffuser",
            email="staff@example.com",
            password="testpass123",
            is_staff=True,
        )
        self.read_perm, _ = APITokenPermission.objects.get_or_create(
            resource="cases", action="read"
        )
        self.staff_group = APITokenPermissionGroup.objects.create(name="staff_group")
        self.staff_group.permissions.add(self.read_perm)
        self.staff_token = APIToken.objects.create(
            user=self.staff_user,
            name="Staff Token",
            permission_group=self.staff_group,
        )

        # Non-staff user + token
        self.regular_user = User.objects.create_user(
            username="regular",
            email="regular@example.com",
            password="testpass123",
            is_staff=False,
        )
        self.regular_group = APITokenPermissionGroup.objects.create(
            name="regular_group"
        )
        self.regular_group.permissions.add(self.read_perm)
        self.regular_token = APIToken.objects.create(
            user=self.regular_user,
            name="Regular Token",
            permission_group=self.regular_group,
        )

        # Sources
        self.source_a, _ = Source.objects.get_or_create(
            name="source_a", defaults={"homepage": "https://example.com/a"}
        )
        self.source_b, _ = Source.objects.get_or_create(
            name="source_b", defaults={"homepage": "https://example.com/b"}
        )

        # Get two courts from different states
        self.court_a = Court.objects.exclude(pk=Court.DEFAULT_ID).first()
        self.court_b = (
            Court.objects.exclude(pk__in=[Court.DEFAULT_ID, self.court_a.pk])
            .exclude(state=self.court_a.state)
            .first()
        )

        # Dates within the last year (default range)
        today = datetime.date.today()
        self.recent_date_1 = today - relativedelta(months=6)
        self.recent_date_2 = today - relativedelta(months=3)
        self.old_date = today - relativedelta(years=2)

        # Create test cases — recent (within default range)
        self.case_recent_1 = Case.objects.create(
            court=self.court_a,
            file_number="STATS-RECENT/01",
            date=self.recent_date_1,
            content="<p>Recent case 1</p>",
            review_status="accepted",
            source=self.source_a,
        )
        self.case_recent_2 = Case.objects.create(
            court=self.court_a,
            file_number="STATS-RECENT/02",
            date=self.recent_date_2,
            content="<p>Recent case 2</p>",
            review_status="accepted",
            source=self.source_a,
        )
        self.case_recent_b = Case.objects.create(
            court=self.court_b,
            file_number="STATS-RECENT/03",
            date=self.recent_date_2,
            content="<p>Recent case from court B</p>",
            review_status="accepted",
            source=self.source_b,
        )

        # Old case — outside default range
        self.case_old = Case.objects.create(
            court=self.court_a,
            file_number="STATS-OLD/01",
            date=self.old_date,
            content="<p>Old case</p>",
            review_status="accepted",
            source=self.source_a,
        )

        # Pending case — within default range
        self.case_pending = Case.objects.create(
            court=self.court_a,
            file_number="STATS-PENDING/01",
            date=self.recent_date_1,
            content="<p>Pending case</p>",
            review_status="pending",
            source=self.source_a,
        )

        self.client = APIClient()

    # ── Helper to build by_court URL with required state filter ──

    def _by_court_url(self, **extra):
        params = {"court__state": self.court_a.state_id}
        params.update(extra)
        return "/api/cases/stats/by_court/", params

    # ── Response structure ──

    def test_sub_endpoint_response_structure(self):
        """Sub-endpoints return filters, total, results (no top-level buckets).

        ``by_source`` is staff-only, so it's covered separately below.
        """
        urls = [
            ("/api/cases/stats/by_country/", {}),
            ("/api/cases/stats/by_state/", {}),
            ("/api/cases/stats/by_court/", {"court__state": self.court_a.state_id}),
        ]
        for url, params in urls:
            response = self.client.get(url, params)
            self.assertEqual(response.status_code, status.HTTP_200_OK, msg=url)
            data = response.data
            self.assertIn("filters", data, msg=url)
            self.assertIn("total", data, msg=url)
            self.assertIn("results", data, msg=url)
            self.assertNotIn("buckets", data, msg=url)
            self.assertIsInstance(data["results"], list, msg=url)

    def test_by_source_response_structure_for_staff(self):
        """Staff get the same structure on by_source as on the public sub-endpoints."""
        self.client.force_authenticate(user=self.staff_user, token=self.staff_token)
        response = self.client.get("/api/cases/stats/by_source/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.data
        self.assertIn("filters", data)
        self.assertIn("total", data)
        self.assertIn("results", data)
        self.assertNotIn("buckets", data)

    def test_result_items_have_total_and_buckets(self):
        """Each result item has its own total and buckets."""
        response = self.client.get("/api/cases/stats/by_state/")
        for item in response.data["results"]:
            self.assertIn("total", item)
            self.assertIn("buckets", item)
            self.assertIsInstance(item["buckets"], list)
            # Bucket counts sum to item total
            bucket_sum = sum(b["count"] for b in item["buckets"])
            self.assertEqual(bucket_sum, item["total"], msg=f"Item {item['id']}")

    def test_root_stats_response_structure(self):
        """GET /api/cases/stats/ returns filters, total, buckets (no results)."""
        response = self.client.get("/api/cases/stats/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.data
        self.assertIn("filters", data)
        self.assertIn("total", data)
        self.assertIn("buckets", data)
        self.assertNotIn("results", data)

    def test_root_stats_total(self):
        """Root endpoint total matches accepted cases in default range."""
        response = self.client.get("/api/cases/stats/")
        self.assertEqual(response.data["total"], 3)

    def test_root_stats_ignores_court_filter(self):
        """Root endpoint ignores court/state/source filters."""
        response = self.client.get("/api/cases/stats/", {"court": self.court_a.pk})
        self.assertEqual(response.data["total"], 3)

    def test_root_stats_staff_review_status(self):
        """Root endpoint supports review_status filter for staff."""
        self.client.force_authenticate(user=self.staff_user, token=self.staff_token)
        response = self.client.get("/api/cases/stats/", {"review_status": "pending"})
        self.assertEqual(response.data["total"], 1)

    def test_root_stats_buckets_sum_to_total(self):
        """Root endpoint buckets sum to total."""
        response = self.client.get("/api/cases/stats/")
        bucket_sum = sum(b["count"] for b in response.data["buckets"])
        self.assertEqual(bucket_sum, response.data["total"])

    # ── Default date range and bucket ──

    def test_default_date_range_last_year(self):
        """Default date range is last year."""
        response = self.client.get("/api/cases/stats/by_state/")
        filters = response.data["filters"]
        today = datetime.date.today()
        one_year_ago = today - relativedelta(years=1)
        self.assertEqual(filters["date_after"], str(one_year_ago))
        self.assertEqual(filters["date_before"], str(today))

    def test_default_bucket_is_month(self):
        """Default bucket is month."""
        response = self.client.get("/api/cases/stats/by_state/")
        self.assertEqual(response.data["filters"]["bucket"], "month")

    def test_default_range_excludes_old_cases(self):
        """Default range (last year) excludes cases older than one year."""
        response = self.client.get("/api/cases/stats/by_state/")
        self.assertEqual(response.data["total"], 3)

    # ── Total count & visibility ──

    def test_anonymous_total_counts_accepted_only(self):
        """Anonymous user sees only accepted cases."""
        response = self.client.get("/api/cases/stats/by_state/")
        self.assertEqual(response.data["total"], 3)

    def test_staff_total_counts_all(self):
        """Staff sees all cases including pending/rejected."""
        self.client.force_authenticate(user=self.staff_user, token=self.staff_token)
        response = self.client.get("/api/cases/stats/by_state/")
        self.assertEqual(response.data["total"], 4)

    def test_non_staff_total_counts_accepted_only(self):
        """Non-staff authenticated user sees accepted + their own."""
        self.client.force_authenticate(user=self.regular_user, token=self.regular_token)
        response = self.client.get("/api/cases/stats/by_state/")
        self.assertEqual(response.data["total"], 3)

    # ── Staff review_status filter ──

    def test_staff_filter_review_status(self):
        """Staff can filter by review_status=pending."""
        self.client.force_authenticate(user=self.staff_user, token=self.staff_token)
        response = self.client.get(
            "/api/cases/stats/by_state/", {"review_status": "pending"}
        )
        self.assertEqual(response.data["total"], 1)

    def test_non_staff_review_status_ignored(self):
        """Non-staff user's review_status param is silently ignored."""
        self.client.force_authenticate(user=self.regular_user, token=self.regular_token)
        response = self.client.get(
            "/api/cases/stats/by_state/", {"review_status": "pending"}
        )
        self.assertEqual(response.data["total"], 3)

    # ── Date range filtering ──

    def test_explicit_date_range_includes_old(self):
        """Explicit date range can include older cases (within bucket cap)."""
        # bucket=year has no range cap — used here so the wide range stays valid.
        response = self.client.get(
            "/api/cases/stats/by_state/",
            {
                "date_after": "2000-01-01",
                "date_before": "2099-12-31",
                "bucket": "year",
            },
        )
        self.assertEqual(response.data["total"], 4)

    def test_narrow_date_range(self):
        """Narrow date range limits results."""
        url, params = self._by_court_url(
            date_after=str(self.recent_date_1),
            date_before=str(self.recent_date_1),
        )
        response = self.client.get(url, params)
        self.assertEqual(response.data["total"], 1)

    # ── Bucket formats (on root endpoint which still has top-level buckets) ──

    def test_bucket_month_format(self):
        """Default bucket=month returns YYYY-MM format in root buckets."""
        response = self.client.get("/api/cases/stats/")
        for item in response.data["buckets"]:
            self.assertRegex(item["date"], r"^\d{4}-\d{2}$")

    def test_bucket_year_format(self):
        """bucket=year returns YYYY format."""
        response = self.client.get("/api/cases/stats/", {"bucket": "year"})
        for item in response.data["buckets"]:
            self.assertRegex(item["date"], r"^\d{4}$")

    def test_bucket_day_format(self):
        """bucket=day returns YYYY-MM-DD format."""
        # bucket=day is capped at 3 months; bound the range explicitly.
        today = datetime.date.today()
        date_after = (today - relativedelta(months=2)).isoformat()
        response = self.client.get(
            "/api/cases/stats/",
            {
                "bucket": "day",
                "date_after": date_after,
                "date_before": today.isoformat(),
            },
        )
        for item in response.data["buckets"]:
            self.assertRegex(item["date"], r"^\d{4}-\d{2}-\d{2}$")

    def test_per_item_bucket_format(self):
        """Per-item buckets use the requested bucket format."""
        today = datetime.date.today()
        date_after = (today - relativedelta(months=2)).isoformat()
        response = self.client.get(
            "/api/cases/stats/by_state/",
            {
                "bucket": "day",
                "date_after": date_after,
                "date_before": today.isoformat(),
            },
        )
        for item in response.data["results"]:
            for b in item["buckets"]:
                self.assertRegex(b["date"], r"^\d{4}-\d{2}-\d{2}$")

    # ── Invalid parameters ──

    def test_invalid_bucket(self):
        """Invalid bucket returns 400."""
        response = self.client.get("/api/cases/stats/by_state/", {"bucket": "invalid"})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_invalid_date_after(self):
        """Invalid date_after returns 400."""
        response = self.client.get(
            "/api/cases/stats/by_state/", {"date_after": "not-a-date"}
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_invalid_date_before(self):
        """Invalid date_before returns 400."""
        response = self.client.get(
            "/api/cases/stats/by_state/", {"date_before": "2020-13-45"}
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_invalid_court_id_returns_400(self):
        """Non-numeric court value returns 400."""
        response = self.client.get(
            "/api/cases/stats/by_state/", {"court": "not-a-number"}
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("court", response.data["detail"])

    def test_invalid_state_id_returns_400(self):
        """Non-numeric court__state value returns 400."""
        response = self.client.get("/api/cases/stats/by_state/", {"court__state": "de"})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("court__state", response.data["detail"])

    def test_invalid_source_id_returns_400(self):
        """Non-numeric source value returns 400."""
        response = self.client.get("/api/cases/stats/by_state/", {"source": "abc"})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("source", response.data["detail"])

    def test_invalid_state_id_on_by_court_returns_400(self):
        """Non-numeric court__state on by_court returns 400, not 500."""
        response = self.client.get("/api/cases/stats/by_court/", {"court__state": "de"})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    # ── by_court requires court__state or state_slug ──

    def test_by_court_requires_state(self):
        """by_court without court__state or state_slug returns 400."""
        response = self.client.get("/api/cases/stats/by_court/")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("court__state", response.data["detail"])

    def test_by_court_with_state_works(self):
        """by_court with court__state returns 200."""
        url, params = self._by_court_url()
        response = self.client.get(url, params)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    # ── by_court grouping ──

    def test_by_court_grouping(self):
        """by_court returns correct per-item totals and buckets."""
        url, params = self._by_court_url()
        response = self.client.get(url, params)
        by_court = {item["id"]: item for item in response.data["results"]}
        self.assertIn(self.court_a.pk, by_court)
        self.assertEqual(by_court[self.court_a.pk]["total"], 2)
        self.assertEqual(by_court[self.court_a.pk]["name"], self.court_a.name)
        self.assertIsInstance(by_court[self.court_a.pk]["buckets"], list)

    # ── by_source grouping (staff-only) ──

    def test_by_source_anonymous_403(self):
        """Anonymous users cannot access by_source."""
        response = self.client.get("/api/cases/stats/by_source/")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_by_source_non_staff_403(self):
        """Non-staff authenticated users cannot access by_source."""
        self.client.force_authenticate(user=self.regular_user, token=self.regular_token)
        response = self.client.get("/api/cases/stats/by_source/")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_by_source_grouping(self):
        """by_source returns correct per-item totals (staff)."""
        self.client.force_authenticate(user=self.staff_user, token=self.staff_token)
        response = self.client.get("/api/cases/stats/by_source/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        by_source = {item["id"]: item for item in response.data["results"]}
        self.assertIn(self.source_a.pk, by_source)
        # Staff sees pending case (source_a) too: 3 accepted + 1 pending on source_a
        self.assertEqual(by_source[self.source_a.pk]["total"], 3)
        self.assertEqual(by_source[self.source_a.pk]["name"], "source_a")
        self.assertIn(self.source_b.pk, by_source)
        self.assertEqual(by_source[self.source_b.pk]["total"], 1)

    # ── by_state grouping ──

    def test_by_state_grouping(self):
        """by_state returns entries with id, name, total, buckets."""
        response = self.client.get("/api/cases/stats/by_state/")
        results = response.data["results"]
        self.assertTrue(len(results) > 0)
        entry = results[0]
        self.assertIn("id", entry)
        self.assertIn("name", entry)
        self.assertIn("total", entry)
        self.assertIn("buckets", entry)
        by_state = {item["id"]: item for item in results}
        self.assertIn(self.court_a.state_id, by_state)

    # ── by_country grouping ──

    def test_by_country_grouping(self):
        """by_country returns entries with id, code, name, total, buckets."""
        response = self.client.get("/api/cases/stats/by_country/")
        results = response.data["results"]
        self.assertTrue(len(results) > 0)
        entry = results[0]
        self.assertIn("id", entry)
        self.assertIn("code", entry)
        self.assertIn("name", entry)
        self.assertIn("total", entry)
        self.assertIn("buckets", entry)

    # ── Optional filters ──

    def test_filter_by_court(self):
        """court= filter narrows results."""
        response = self.client.get(
            "/api/cases/stats/by_state/", {"court": self.court_a.pk}
        )
        self.assertEqual(response.data["total"], 2)

    def test_filter_by_state(self):
        """court__state= filter narrows results on by_state."""
        response = self.client.get(
            "/api/cases/stats/by_state/",
            {"court__state": self.court_a.state_id},
        )
        self.assertGreaterEqual(response.data["total"], 2)

    def test_filter_by_source(self):
        """source= filter narrows results."""
        url, params = self._by_court_url(source=self.source_a.pk)
        response = self.client.get(url, params)
        self.assertEqual(response.data["total"], 2)

    # ── Empty results ──

    def test_empty_result(self):
        """No matching cases returns total=0 and empty results."""
        url, params = self._by_court_url(date_after="2099-01-01")
        response = self.client.get(url, params)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["total"], 0)
        self.assertEqual(response.data["results"], [])

    # ── Read-only ──

    def test_post_not_allowed(self):
        """POST to stats endpoints is not allowed."""
        urls = [
            "/api/cases/stats/by_country/",
            "/api/cases/stats/by_state/",
            "/api/cases/stats/by_court/",
            "/api/cases/stats/by_source/",
        ]
        for url in urls:
            response = self.client.post(url, {}, format="json")
            self.assertEqual(
                response.status_code,
                status.HTTP_405_METHOD_NOT_ALLOWED,
                msg=url,
            )

    # ── Filters reflected in response ──

    def test_filters_in_response(self):
        """Response filters reflect the query parameters."""
        url, params = self._by_court_url(
            date_after="2020-01-01",
            date_before="2023-12-31",
            bucket="year",
        )
        response = self.client.get(url, params)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        filters = response.data["filters"]
        self.assertEqual(filters["date_after"], "2020-01-01")
        self.assertEqual(filters["date_before"], "2023-12-31")
        self.assertEqual(filters["bucket"], "year")

    # ── Results sorted by total descending ──

    def test_results_sorted_by_total_descending(self):
        """Results are sorted by total in descending order."""
        response = self.client.get("/api/cases/stats/by_state/")
        totals = [item["total"] for item in response.data["results"]]
        self.assertEqual(totals, sorted(totals, reverse=True))

    # ── Slug-based filtering ──

    def test_filter_by_court_slug(self):
        """court_slug filter returns same results as court ID filter."""
        response_id = self.client.get(
            "/api/cases/stats/by_state/", {"court": self.court_a.pk}
        )
        response_slug = self.client.get(
            "/api/cases/stats/by_state/", {"court_slug": self.court_a.slug}
        )
        self.assertEqual(response_id.status_code, status.HTTP_200_OK)
        self.assertEqual(response_slug.status_code, status.HTTP_200_OK)
        self.assertEqual(response_id.data["total"], response_slug.data["total"])

    def test_filter_by_state_slug(self):
        """state_slug filter returns same results as court__state ID filter."""
        state = self.court_a.state
        response_id = self.client.get(
            "/api/cases/stats/by_state/", {"court__state": state.pk}
        )
        response_slug = self.client.get(
            "/api/cases/stats/by_state/", {"state_slug": state.slug}
        )
        self.assertEqual(response_id.status_code, status.HTTP_200_OK)
        self.assertEqual(response_slug.status_code, status.HTTP_200_OK)
        self.assertEqual(response_id.data["total"], response_slug.data["total"])

    def test_by_court_with_state_slug(self):
        """by_court works with state_slug instead of court__state."""
        state = self.court_a.state
        response = self.client.get(
            "/api/cases/stats/by_court/", {"state_slug": state.slug}
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(response.data["total"], 2)

    def test_nonexistent_court_slug_returns_empty(self):
        """Nonexistent court_slug returns 200 with total=0."""
        response = self.client.get(
            "/api/cases/stats/by_state/", {"court_slug": "nonexistent-court"}
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["total"], 0)

    def test_nonexistent_state_slug_returns_empty(self):
        """Nonexistent state_slug returns 200 with total=0."""
        response = self.client.get(
            "/api/cases/stats/by_state/", {"state_slug": "nonexistent-state"}
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["total"], 0)

    # ── Per-bucket date range cap ──

    def test_day_bucket_rejects_range_over_three_months(self):
        """bucket=day is capped at a 3-month span."""
        response = self.client.get(
            "/api/cases/stats/",
            {
                "bucket": "day",
                "date_after": "2024-01-01",
                "date_before": "2024-06-01",
            },
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("3 months", response.data["detail"])
        self.assertIn("day", response.data["detail"])

    def test_day_bucket_accepts_three_month_range(self):
        """bucket=day accepts an exactly-3-month span."""
        response = self.client.get(
            "/api/cases/stats/",
            {
                "bucket": "day",
                "date_after": "2024-01-01",
                "date_before": "2024-04-01",
            },
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_month_bucket_rejects_range_over_five_years(self):
        """bucket=month is capped at a 5-year span."""
        response = self.client.get(
            "/api/cases/stats/",
            {
                "bucket": "month",
                "date_after": "2018-01-01",
                "date_before": "2024-01-02",
            },
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("5 years", response.data["detail"])
        self.assertIn("month", response.data["detail"])

    def test_month_bucket_accepts_five_year_range(self):
        """bucket=month accepts an exactly-5-year span."""
        response = self.client.get(
            "/api/cases/stats/",
            {
                "bucket": "month",
                "date_after": "2019-01-01",
                "date_before": "2024-01-01",
            },
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_year_bucket_has_no_range_cap(self):
        """bucket=year has no range cap (yearly counts compress fine)."""
        response = self.client.get(
            "/api/cases/stats/",
            {
                "bucket": "year",
                "date_after": "1900-01-01",
                "date_before": "2099-12-31",
            },
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_range_cap_applies_on_sub_endpoint(self):
        """Range cap also applies to sub-endpoints like by_state."""
        response = self.client.get(
            "/api/cases/stats/by_state/",
            {
                "bucket": "day",
                "date_after": "2024-01-01",
                "date_before": "2025-01-01",
            },
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
