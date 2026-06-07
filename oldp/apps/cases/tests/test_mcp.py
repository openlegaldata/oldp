"""Unit tests for case MCP tools."""

from datetime import date, timedelta
from unittest.mock import MagicMock, patch

from django.test import TestCase, override_settings

from oldp.apps.cases.mcp import CaseTools, _match_quality, _norm_court
from oldp.apps.cases.models import Case
from oldp.apps.courts.models import Court


@override_settings(
    CACHES={"default": {"BACKEND": "django.core.cache.backends.dummy.DummyCache"}}
)
class CaseToolsTests(TestCase):
    """Tests for case search, filter, retrieval, and statistics MCP tools."""

    fixtures = [
        "locations/countries.json",
        "locations/states.json",
        "locations/cities.json",
        "courts/courts.json",
    ]

    def setUp(self):
        self.tools = CaseTools()
        self.court = Court.objects.filter(review_status="accepted").first()
        # Create test cases
        if self.court:
            self.case1 = Case.objects.create(
                court=self.court,
                file_number="I ZR 100/21",
                date=date(2023, 6, 15),
                content="<p>This is a test case about tort law.</p>",
                type="Urteil",
                ecli="ECLI:DE:BGH:2023:150623UIZR100.21.0",
                slug="test-case-1",
                review_status="accepted",
            )
            self.case2 = Case.objects.create(
                court=self.court,
                file_number="II ZR 200/22",
                date=date(2024, 3, 10),
                content="<p>Another test case about contract law.</p>",
                type="Beschluss",
                slug="test-case-2",
                review_status="accepted",
            )
            self.pending_case = Case.objects.create(
                court=self.court,
                file_number="III ZR 300/23",
                date=date(2024, 1, 1),
                content="<p>Pending case.</p>",
                slug="test-case-pending",
                review_status="pending",
            )

    # --- get_similar_cases tests ---

    def _patch_backend(self, hits):
        """Return a context-manager patch of haystack.connections whose
        backend's conn.search yields ``hits`` (list of django_id strings).
        Exposes the captured search call via ``fake_backend.conn.search``.
        """
        fake_backend = MagicMock()
        fake_backend.index_name = "oldp"
        fake_backend.conn.search.return_value = {
            "hits": {"hits": [{"_source": {"django_id": h}} for h in hits]}
        }
        conn = MagicMock()
        conn.get_backend.return_value = fake_backend
        return patch("haystack.connections", {"default": conn}), fake_backend

    def test_get_similar_cases_not_found(self):
        result = self.tools.get_similar_cases(case_id=999999)
        self.assertIn("error", result)

    def test_get_similar_cases_orders_and_hydrates(self):
        if not self.court:
            self.skipTest("no court fixture loaded")
        # ES returns case2 first (more similar), then the pending case id
        # which must be dropped on DB hydration (review_status != accepted).
        ctx, fake_backend = self._patch_backend(
            [str(self.case2.id), str(self.pending_case.id)]
        )
        with ctx:
            result = self.tools.get_similar_cases(case_id=self.case1.id)
        self.assertEqual(result["seed_case_id"], self.case1.id)
        self.assertEqual([r["id"] for r in result["results"]], [self.case2.id])

    def test_get_similar_cases_query_excludes_seed_and_scopes_cases(self):
        if not self.court:
            self.skipTest("no court fixture loaded")
        ctx, fake_backend = self._patch_backend([])
        with ctx:
            self.tools.get_similar_cases(case_id=self.case1.id)
        body = fake_backend.conn.search.call_args.kwargs["body"]
        bool_q = body["query"]["bool"]
        self.assertEqual(
            bool_q["must"]["more_like_this"]["like"][0]["_id"],
            f"cases.case.{self.case1.id}",
        )
        self.assertIn({"term": {"django_id": str(self.case1.id)}}, bool_q["must_not"])
        self.assertIn({"term": {"django_ct": "cases.case"}}, bool_q["filter"])

    def test_get_similar_cases_clamps_limit(self):
        if not self.court:
            self.skipTest("no court fixture loaded")
        ctx, fake_backend = self._patch_backend([])
        with ctx:
            result = self.tools.get_similar_cases(case_id=self.case1.id, limit=999)
        self.assertTrue(result["limit_clamped"])
        self.assertEqual(result["requested_limit"], 999)
        self.assertEqual(fake_backend.conn.search.call_args.kwargs["body"]["size"], 50)

    def test_get_similar_cases_timeout_is_retryable(self):
        if not self.court:
            self.skipTest("no court fixture loaded")
        from elasticsearch.exceptions import ConnectionTimeout

        ctx, fake_backend = self._patch_backend([])
        fake_backend.conn.search.side_effect = ConnectionTimeout(
            "TIMEOUT", "read timed out", None
        )
        with ctx:
            result = self.tools.get_similar_cases(case_id=self.case1.id)
        self.assertTrue(result["retryable"])
        self.assertIn("hint", result)

    # --- filter_cases tests ---

    def test_filter_cases_returns_results(self):
        result = self.tools.filter_cases()
        self.assertIn("results", result)
        self.assertIn("total", result)

    def test_filter_cases_by_court(self):
        if self.court:
            result = self.tools.filter_cases(court_id=self.court.id)
            for c in result["results"]:
                self.assertIsNotNone(c["court_name"])

    def test_filter_cases_by_file_number(self):
        result = self.tools.filter_cases(file_number="I ZR 100/21")
        self.assertEqual(result["total"], 1)
        self.assertEqual(result["results"][0]["file_number"], "I ZR 100/21")

    def test_filter_cases_by_ecli(self):
        result = self.tools.filter_cases(ecli="ECLI:DE:BGH:2023:150623UIZR100.21.0")
        self.assertEqual(result["total"], 1)

    def test_filter_cases_by_date_range(self):
        result = self.tools.filter_cases(
            date_after="2024-01-01", date_before="2024-12-31"
        )
        for c in result["results"]:
            self.assertGreaterEqual(c["date"], "2024-01-01")
            self.assertLessEqual(c["date"], "2024-12-31")

    def test_filter_cases_by_decision_type(self):
        result = self.tools.filter_cases(decision_type="Urteil")
        for c in result["results"]:
            self.assertIn("Urteil", c["type"])

    def test_filter_cases_excludes_pending(self):
        result = self.tools.filter_cases()
        ids = [c["id"] for c in result["results"]]
        if hasattr(self, "pending_case"):
            self.assertNotIn(self.pending_case.id, ids)

    def test_filter_cases_limit(self):
        result = self.tools.filter_cases(limit=1)
        self.assertLessEqual(len(result["results"]), 1)

    def test_filter_cases_offset(self):
        result_all = self.tools.filter_cases(limit=50)
        result_offset = self.tools.filter_cases(limit=50, offset=1)
        if len(result_all["results"]) > 1:
            self.assertEqual(
                result_offset["results"][0]["id"],
                result_all["results"][1]["id"],
            )

    def test_filter_cases_invalid_date(self):
        result = self.tools.filter_cases(date_after="not-a-date")
        self.assertIn("error", result)

    def test_filter_cases_no_results(self):
        result = self.tools.filter_cases(file_number="NONEXISTENT-999/99")
        self.assertIn("message", result)
        self.assertEqual(result["total"], 0)

    def test_filter_cases_result_fields(self):
        result = self.tools.filter_cases()
        if result["results"]:
            case = result["results"][0]
            self.assertIn("id", case)
            self.assertIn("slug", case)
            self.assertIn("file_number", case)
            self.assertIn("date", case)
            self.assertIn("court_name", case)
            self.assertIn("type", case)
            self.assertIn("ecli", case)

    # --- get_case tests ---

    def test_get_case_by_id(self):
        if hasattr(self, "case1"):
            result = self.tools.get_case(case_id=self.case1.id)
            self.assertEqual(result["id"], self.case1.id)
            self.assertIn("content", result)

    def test_get_case_by_slug(self):
        if hasattr(self, "case1"):
            result = self.tools.get_case(slug=self.case1.slug)
            self.assertEqual(result["id"], self.case1.id)

    def test_get_case_not_found(self):
        result = self.tools.get_case(case_id=999999)
        self.assertIn("error", result)

    def test_get_case_no_params(self):
        result = self.tools.get_case()
        self.assertIn("error", result)

    def test_get_case_content_truncation(self):
        if not self.court:
            self.skipTest("No court fixture")
        # Create a case with very long content
        long_content = "x" * 50000
        big_case = Case.objects.create(
            court=self.court,
            file_number="BIG/01",
            content=long_content,
            slug="test-big-case",
            review_status="accepted",
        )
        result = self.tools.get_case(case_id=big_case.id, full_text=False)
        self.assertTrue(result["content_truncated"])
        self.assertLessEqual(len(result["content"]), 31000)

    def test_get_case_full_text(self):
        if not self.court:
            self.skipTest("No court fixture")
        long_content = "x" * 50000
        big_case = Case.objects.create(
            court=self.court,
            file_number="BIG/02",
            content=long_content,
            slug="test-big-case-2",
            review_status="accepted",
        )
        result = self.tools.get_case(case_id=big_case.id, full_text=True)
        self.assertFalse(result["content_truncated"])

    def test_get_case_has_court_info(self):
        if hasattr(self, "case1"):
            result = self.tools.get_case(case_id=self.case1.id)
            self.assertIn("court", result)
            self.assertIn("name", result["court"])
            self.assertIn("slug", result["court"])

    def test_get_case_excludes_pending(self):
        if hasattr(self, "pending_case"):
            result = self.tools.get_case(case_id=self.pending_case.id)
            self.assertIn("error", result)

    # --- search_cases tests ---

    def test_search_cases_returns_dict(self):
        result = self.tools.search_cases(query="test")
        self.assertIsInstance(result, dict)

    def test_search_cases_handles_es_failure(self):
        result = self.tools.search_cases(query="tort law")
        self.assertTrue("results" in result or "error" in result)

    def _patched_search_cases(self, **kwargs):
        """Run search_cases against a fake queryset; return (result, filters)."""

        class FakeSearchQuerySet:
            def __init__(self):
                self.filters = []
                self.order_by_calls = []

            def auto_query(self, query):
                return self

            def filter(self, **kwargs):
                self.filters.append(kwargs)
                return self

            def order_by(self, *fields):
                self.order_by_calls.extend(fields)
                return self

            def __getitem__(self, key):
                return []

        class FakeSearchQueryBuilder:
            def __init__(self):
                self.sqs = FakeSearchQuerySet()

            def filter_models(self, models):
                return self

            def filter_review_status(self, status):
                return self

            def apply_highlight(self):
                return self

            def apply_date_range(self, start_date, end_date):
                return self

            def build(self):
                return self.sqs

        builder = FakeSearchQueryBuilder()
        with patch("oldp.apps.search.api.SearchQueryBuilder", return_value=builder):
            result = self.tools.search_cases(**kwargs)
        self._last_order_by = builder.sqs.order_by_calls
        return result, builder.sqs.filters

    def test_search_cases_sort_relevance_does_not_order(self):
        self._patched_search_cases(query="test")
        self.assertEqual(self._last_order_by, [])

    def test_search_cases_sort_date(self):
        self._patched_search_cases(query="test", sort="date")
        self.assertIn("-date", self._last_order_by)

    def test_search_cases_sort_most_cited(self):
        self._patched_search_cases(query="test", sort="most_cited")
        self.assertIn("-citing_cases_count", self._last_order_by)

    def test_match_quality_binning(self):
        # Relative to the top score: high >= 0.66, medium >= 0.33, else low.
        self.assertEqual(_match_quality(100, 100), "high")
        self.assertEqual(_match_quality(70, 100), "high")
        self.assertEqual(_match_quality(50, 100), "medium")
        self.assertEqual(_match_quality(20, 100), "low")

    def test_match_quality_none_without_score(self):
        self.assertIsNone(_match_quality(None, 100))
        self.assertIsNone(_match_quality(50, None))
        self.assertIsNone(_match_quality(50, 0))

    def test_norm_court_unknown_becomes_none(self):
        self.assertIsNone(_norm_court("unknown"))
        self.assertIsNone(_norm_court("Unknown"))
        self.assertEqual(_norm_court("BGH"), "BGH")
        # Non-placeholder values pass through unchanged.
        self.assertEqual(_norm_court(""), "")

    def test_search_cases_uses_exact_facet_filters(self):
        result, filters = self._patched_search_cases(
            query="test",
            court_code="BGH",
            decision_type="Urteil",
        )
        self.assertEqual(result["total"], 0)
        self.assertIn({"court_exact": "BGH"}, filters)
        self.assertIn({"decision_type_exact": "Urteil"}, filters)

    def test_search_cases_always_constrains_to_case_index(self):
        """Regression test (symmetric to the search_laws fix).

        search_cases must filter on facet_model_name_exact="Case" regardless
        of whether court_code or decision_type are set. The custom
        SearchBackend silently drops the .models() filter, so without this
        guard a query that also matches Law text could leak Law results.
        """
        # No facet args -> the bug-prone path.
        _, filters_no_facets = self._patched_search_cases(query="test")
        self.assertIn({"facet_model_name_exact": "Case"}, filters_no_facets)

        # With facet args -> filter is still applied.
        _, filters_with_facets = self._patched_search_cases(
            query="test", court_code="BGH", decision_type="Urteil"
        )
        self.assertIn({"facet_model_name_exact": "Case"}, filters_with_facets)

    def test_search_cases_chains_law_citation_filter(self):
        """``cited_law_book`` + ``cited_law_section`` must chain a
        ``cited_laws=<book>__<section>`` filter onto the keyword
        query so MCP clients can run combined searches in one call.
        """
        _, filters = self._patched_search_cases(
            query="mietrecht",
            cited_law_book="bgb",
            cited_law_section="823",
        )
        self.assertIn({"cited_laws": "bgb__823"}, filters)

    def test_search_cases_chains_case_citation_filter(self):
        _, filters = self._patched_search_cases(query="foo", cited_case_id=42)
        self.assertIn({"cited_cases": "42"}, filters)

    def test_search_cases_ignores_zero_cited_case_id(self):
        """``cited_case_id=0`` is the default sentinel for "not supplied"
        and must not produce a citation filter.
        """
        _, filters = self._patched_search_cases(query="foo", cited_case_id=0)
        for f in filters:
            self.assertNotIn("cited_cases", f)

    def test_search_cases_partial_law_citation_is_ignored(self):
        """``cited_law_book`` without ``cited_law_section`` (or vice
        versa) should be ignored — the helper requires both.
        """
        _, filters = self._patched_search_cases(query="foo", cited_law_book="bgb")
        for f in filters:
            self.assertNotIn("cited_laws", f)

    # --- get_case_statistics tests ---

    def test_get_case_statistics_returns_dict(self):
        result = self.tools.get_case_statistics()
        self.assertIsInstance(result, dict)
        self.assertIn("total", result)
        self.assertIn("time_series", result)
        self.assertIn("top_courts", result)

    def test_get_case_statistics_group_by_year(self):
        result = self.tools.get_case_statistics(group_by="year")
        for bucket in result["time_series"]:
            self.assertEqual(len(bucket["date"]), 4)  # YYYY format

    def test_get_case_statistics_with_date_range(self):
        result = self.tools.get_case_statistics(
            date_after="2023-01-01", date_before="2023-12-31"
        )
        self.assertIsInstance(result["total"], int)

    def test_filter_cases_excludes_future_dated(self):
        """Regression test.

        Production showed cases dated 2026/2027/2029 polluting "newest"
        listings — date-extraction errors during ingestion. Filter them
        out at the MCP boundary while still letting `get_case(id=...)`
        retrieve a specific row by id (single-lookup escape hatch).
        """
        if not self.court:
            self.skipTest("No court fixture")
        far_future = date.today() + timedelta(days=365 * 3)
        future_case = Case.objects.create(
            court=self.court,
            file_number="FUT 001/99",
            date=far_future,
            content="<p>Bogus future-dated case.</p>",
            slug="future-test-case",
            review_status="accepted",
        )

        listing = self.tools.filter_cases(court_id=self.court.id, limit=50)
        listed_ids = [c["id"] for c in listing["results"]]
        self.assertNotIn(
            future_case.id,
            listed_ids,
            msg=(
                "Future-dated case leaked into filter_cases results. "
                "exclude_future_dated_cases is not being applied."
            ),
        )

        # filter_cases by exact file_number must still find it — wait,
        # actually no: filter_cases uses the same queryset, so the
        # future-date filter applies there too. That's intentional —
        # filter_cases is a listing endpoint. Direct retrieval is via
        # get_case.
        direct = self.tools.get_case(case_id=future_case.id)
        self.assertEqual(
            direct.get("id"),
            future_case.id,
            msg="get_case(id=...) must remain a single-lookup escape hatch",
        )

    def test_get_case_statistics_excludes_future_dated(self):
        """Future-dated cases must not appear in stat aggregates either."""
        if not self.court:
            self.skipTest("No court fixture")
        far_future = date.today() + timedelta(days=365 * 3)
        Case.objects.create(
            court=self.court,
            file_number="FUT 002/99",
            date=far_future,
            content="<p>Bogus future-dated case.</p>",
            slug="future-test-case-stats",
            review_status="accepted",
        )

        # Use a wide window that would include the future date if the
        # filter weren't applied.
        result = self.tools.get_case_statistics(
            court_id=self.court.id,
            date_after=str(date.today() - timedelta(days=365)),
            date_before=str(far_future + timedelta(days=1)),
        )
        # The future bucket must not appear.
        future_year = str(far_future.year)
        future_buckets = [b for b in result["time_series"] if future_year in b["date"]]
        self.assertEqual(
            future_buckets,
            [],
            msg=(
                "get_case_statistics included a bogus future-year "
                f"bucket: {future_buckets}"
            ),
        )

    def test_get_case_statistics_jurisdiction_english_alias(self):
        """Regression test.

        The English shortcut "labor" should be translated to the stored
        German "Arbeitsgerichtsbarkeit" before filtering, so that
        get_case_statistics(jurisdiction="labor") matches case rows
        whose court.jurisdiction is in German.
        """
        if not self.court:
            self.skipTest("No court fixture")
        # Configure the fixture court with a German jurisdiction value.
        self.court.jurisdiction = "Arbeitsgerichtsbarkeit"
        self.court.save(update_fields=["jurisdiction"])

        en = self.tools.get_case_statistics(
            jurisdiction="labor",
            date_after="2023-01-01",
            date_before="2024-12-31",
        )
        de = self.tools.get_case_statistics(
            jurisdiction="Arbeitsgerichtsbarkeit",
            date_after="2023-01-01",
            date_before="2024-12-31",
        )
        # Both forms should produce the same totals.
        self.assertEqual(en["total"], de["total"])
        # And the total should be > 0 because self.case1 / self.case2
        # in setUp belong to self.court, which now has a labour
        # jurisdiction.
        self.assertGreaterEqual(en["total"], 1)
