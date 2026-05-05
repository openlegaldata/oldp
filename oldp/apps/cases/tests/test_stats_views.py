"""Tests for the case statistics frontend pages.

Tests cover:
- All stats pages return 200
- Pages contain chart canvas element
- Pages contain sidebar navigation links
- Pages contain correct API endpoint in init script
- Breadcrumbs present
- by_court page has state selector
- Footer contains stats link
- Court detail page contains deep link to stats
"""

from django.contrib.auth.models import User
from django.test import Client, override_settings, tag
from django.urls import reverse

from oldp.apps.courts.models import Court
from oldp.apps.lib.tests import ExtendedLiveServerTestCase


@tag("views")
@override_settings(
    CACHES={"default": {"BACKEND": "django.core.cache.backends.dummy.DummyCache"}},
    STORAGES={
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"
        },
    },
)
class CaseStatsViewsTestCase(ExtendedLiveServerTestCase):
    """Tests for case statistics frontend pages."""

    fixtures = [
        "locations/countries.json",
        "locations/states.json",
        "locations/cities.json",
        "courts/courts.json",
    ]

    def setUp(self):
        self.user = User.objects.create_user("testuser", "test@example.com", "testpass")
        self.user_client = Client()
        self.user_client.force_login(self.user)
        # Staff client for by_source page (staff-only).
        self.staff_user = User.objects.create_user(
            "staffuser", "staff@example.com", "testpass", is_staff=True
        )
        self.staff_client = Client()
        self.staff_client.force_login(self.staff_user)

    # ── Pages return 200 ──

    def test_overview_page(self):
        res = self.client.get(reverse("cases:stats"))
        self.assertEqual(res.status_code, 200)

    def test_by_country_page(self):
        res = self.client.get(reverse("cases:stats_by_country"))
        self.assertEqual(res.status_code, 200)

    def test_by_state_page(self):
        res = self.client.get(reverse("cases:stats_by_state"))
        self.assertEqual(res.status_code, 200)

    def test_by_court_page(self):
        res = self.client.get(reverse("cases:stats_by_court"))
        self.assertEqual(res.status_code, 200)

    def test_by_source_page_staff(self):
        res = self.staff_client.get(reverse("cases:stats_by_source"))
        self.assertEqual(res.status_code, 200)

    def test_by_source_page_anonymous_403(self):
        res = self.client.get(reverse("cases:stats_by_source"))
        self.assertEqual(res.status_code, 403)

    def test_by_source_page_non_staff_403(self):
        res = self.user_client.get(reverse("cases:stats_by_source"))
        self.assertEqual(res.status_code, 403)

    # ── Chart canvas present ──

    def test_overview_has_canvas(self):
        res = self.client.get(reverse("cases:stats"))
        self.assertContains(res, '<canvas id="stats-chart"')

    def test_sub_pages_have_canvas(self):
        public_pages = ["stats_by_country", "stats_by_state", "stats_by_court"]
        for name in public_pages:
            res = self.client.get(reverse("cases:" + name))
            self.assertContains(res, '<canvas id="stats-chart"', msg_prefix=name)
        # by_source is staff-only.
        res = self.staff_client.get(reverse("cases:stats_by_source"))
        self.assertContains(
            res, '<canvas id="stats-chart"', msg_prefix="stats_by_source"
        )

    # ── Sidebar nav links ──

    def test_overview_has_nav_links(self):
        res = self.client.get(reverse("cases:stats"))
        self.assertContains(res, reverse("cases:stats_by_country"))
        self.assertContains(res, reverse("cases:stats_by_state"))
        self.assertContains(res, reverse("cases:stats_by_court"))
        # by_source link is hidden for non-staff.
        self.assertNotContains(res, reverse("cases:stats_by_source"))

    def test_overview_staff_sees_by_source_link(self):
        res = self.staff_client.get(reverse("cases:stats"))
        self.assertContains(res, reverse("cases:stats_by_source"))

    def test_sub_page_has_nav_links(self):
        res = self.client.get(reverse("cases:stats_by_state"))
        self.assertContains(res, reverse("cases:stats"))
        self.assertContains(res, reverse("cases:stats_by_country"))
        self.assertContains(res, reverse("cases:stats_by_court"))
        self.assertNotContains(res, reverse("cases:stats_by_source"))

    # ── API endpoint in init script ──

    def test_overview_api_endpoint(self):
        res = self.client.get(reverse("cases:stats"))
        self.assertContains(res, "apiEndpoint: ''")

    def test_by_country_api_endpoint(self):
        res = self.client.get(reverse("cases:stats_by_country"))
        self.assertContains(res, "apiEndpoint: 'by_country/'")

    def test_by_court_api_endpoint(self):
        res = self.client.get(reverse("cases:stats_by_court"))
        self.assertContains(res, "apiEndpoint: 'by_court/'")

    # ── Breadcrumbs ──

    def test_overview_breadcrumbs(self):
        res = self.client.get(reverse("cases:stats"))
        self.assertContains(res, "Statistics")
        self.assertContains(res, "breadcrumb")

    # ── by_court has state selector ──

    def test_by_court_has_state_select(self):
        res = self.client.get(reverse("cases:stats_by_court"))
        self.assertContains(res, 'id="stats-state"')
        self.assertContains(res, "<option")

    def test_other_pages_no_state_select(self):
        # by_source is staff-only; use staff client to render the page.
        res = self.staff_client.get(reverse("cases:stats_by_source"))
        self.assertNotContains(res, 'id="stats-state"')

    # ── Footer link ──

    def test_footer_has_stats_link(self):
        res = self.client.get(reverse("cases:stats"))
        self.assertContains(res, reverse("cases:stats"))
        self.assertContains(res, "Statistics")

    # ── Court detail deep link ──

    def test_court_detail_has_stats_link(self):
        court = Court.objects.exclude(pk=Court.DEFAULT_ID).first()
        res = self.client.get(reverse("courts:detail", args=(court.slug,)))
        expected_url = (
            reverse("cases:stats_by_court") + "?court__state=" + str(court.state_id)
        )
        self.assertContains(res, expected_url)

    # ── Date filter controls ──

    def test_pages_have_date_filters(self):
        res = self.client.get(reverse("cases:stats"))
        self.assertContains(res, 'id="stats-date-after"')
        self.assertContains(res, 'id="stats-date-before"')
        self.assertContains(res, 'id="stats-bucket"')

    def test_pages_have_quick_date_links(self):
        res = self.client.get(reverse("cases:stats"))
        self.assertContains(res, "StatsApp.setRange")

    # ── Download link ──

    def test_pages_have_download_link(self):
        res = self.client.get(reverse("cases:stats"))
        self.assertContains(res, 'id="stats-download-link"')

    # ── Overview has explore cards ──

    def test_overview_has_explore_cards(self):
        res = self.client.get(reverse("cases:stats"))
        self.assertContains(res, "Explore by Dimension")
