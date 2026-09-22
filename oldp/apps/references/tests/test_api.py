"""Tests for the citation REST API.

Covers the nested actions on ``CaseViewSet`` / ``LawViewSet`` and the
flat ``/api/references/`` resource. The MCP tests in
``test_mcp.py`` exercise the same underlying service-layer code via the
MCP toolset, so this file deliberately focuses on the new HTTP surfaces:
URL routing, serialization, slug-based filtering, and the
``/api/citations/validate/`` procedural endpoint.
"""

from datetime import date

from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from oldp.apps.cases.models import Case
from oldp.apps.courts.models import Country, Court, State
from oldp.apps.laws.models import Law, LawBook
from oldp.apps.references.models import (
    CaseReferenceMarker,
    LawReferenceMarker,
    Reference,
    ReferenceFromCase,
    ReferenceFromLaw,
)
from oldp.apps.references.tests._es_shim import ESCitingCasesShimMixin


def _make_court(slug: str, code: str | None = None) -> Court:
    de, _ = Country.objects.get_or_create(code="DE", defaults={"name": "Germany"})
    state, _ = State.objects.get_or_create(
        pk=1, defaults={"name": "Test", "country": de, "slug": "test"}
    )
    return Court.objects.create(
        name=f"Court {slug}",
        slug=slug,
        code=code or slug.upper()[:20],
        state=state,
        review_status="accepted",
    )


def _make_book(slug: str, code: str) -> LawBook:
    return LawBook.objects.create(
        code=code,
        title=code,
        slug=slug,
        latest=True,
        revision_date="2024-01-01",
        review_status="accepted",
    )


def _make_law(book: LawBook, section: str, slug: str) -> Law:
    return Law.objects.create(
        book=book,
        section=section,
        slug=slug,
        review_status="accepted",
    )


def _make_case(court: Court, file_number: str, slug: str) -> Case:
    return Case.objects.create(
        court=court,
        file_number=file_number,
        slug=slug,
        date=date(2024, 1, 1),
        ecli=f"ECLI:DE:TEST:{slug}",
        review_status="accepted",
    )


def _attach_case_law_ref(case: Case, law: Law, marker_text: str = "§ 1 BGB") -> None:
    marker = CaseReferenceMarker.objects.create(
        referenced_by=case, text=marker_text, start=0, end=len(marker_text)
    )
    ref = Reference.objects.create(law=law, to=marker_text)
    ref.set_to_hash()
    ref.save()
    ReferenceFromCase.objects.create(marker=marker, reference=ref)


def _attach_case_case_ref(source: Case, target: Case, marker_text: str) -> None:
    marker = CaseReferenceMarker.objects.create(
        referenced_by=source, text=marker_text, start=0, end=len(marker_text)
    )
    ref = Reference.objects.create(case=target, to=marker_text)
    ref.set_to_hash()
    ref.save()
    ReferenceFromCase.objects.create(marker=marker, reference=ref)


def _attach_law_law_ref(source: Law, target: Law, marker_text: str = "§ 1") -> None:
    marker = LawReferenceMarker.objects.create(
        referenced_by=source, text=marker_text, start=0, end=len(marker_text)
    )
    ref = Reference.objects.create(law=target, to=marker_text)
    ref.set_to_hash()
    ref.save()
    ReferenceFromLaw.objects.create(marker=marker, reference=ref)


@override_settings(
    CACHES={"default": {"BACKEND": "django.core.cache.backends.dummy.DummyCache"}}
)
class CitationApiTestCase(ESCitingCasesShimMixin, TestCase):
    """Exercise nested + flat citation surfaces."""

    @classmethod
    def setUpTestData(cls):
        # Books + laws
        cls.bgb = _make_book("bgb", "BGB")
        cls.law_823 = _make_law(cls.bgb, "§ 823", "823")
        cls.law_249 = _make_law(cls.bgb, "§ 249", "249")
        cls.gg = _make_book("gg", "GG")
        cls.gg_art1 = _make_law(cls.gg, "Artikel 1", "artikel-1")

        # Courts + cases
        cls.bgh = _make_court("bgh", "BGH")
        cls.lg = _make_court("lg-koln", "LGK")
        cls.case_a = _make_case(cls.bgh, "VI ZR 1/24", "bgh-vi-zr-124")
        cls.case_b = _make_case(cls.lg, "1 O 100/24", "lg-1-o-10024")
        cls.case_c = _make_case(cls.bgh, "VI ZR 2/24", "bgh-vi-zr-224")

        # Forward refs from case_a: cites §823 BGB and case_b
        _attach_case_law_ref(cls.case_a, cls.law_823, "§ 823 BGB")
        _attach_case_case_ref(cls.case_a, cls.case_b, "1 O 100/24")
        # case_c also cites §823 → makes the law's citing_cases set
        _attach_case_law_ref(cls.case_c, cls.law_823, "§ 823 BGB")
        # Forward refs from law_823 → law_249 (intra-book)
        _attach_law_law_ref(cls.law_823, cls.law_249, "§ 249")

    def setUp(self):
        self.client = APIClient()

    # --- Nested actions on CaseViewSet ----------------------------------

    def test_case_references_action(self):
        """``/api/cases/<id>/references/`` returns the forward-refs dict."""
        resp = self.client.get(f"/api/cases/{self.case_a.id}/references/")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["case_id"], self.case_a.id)
        self.assertEqual(body["total_law_references"], 1)
        self.assertEqual(body["total_case_references"], 1)
        self.assertEqual(body["law_references"][0]["id"], self.law_823.id)
        self.assertEqual(body["case_references"][0]["id"], self.case_b.id)

    def test_case_citing_cases_action(self):
        """``/api/cases/<id>/citing_cases/`` paginates."""
        resp = self.client.get(f"/api/cases/{self.case_b.id}/citing_cases/")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["count"], 1)
        self.assertEqual(body["results"][0]["id"], self.case_a.id)

    def test_case_citing_laws_action_empty(self):
        """No laws cite a fixture case in this scenario."""
        resp = self.client.get(f"/api/cases/{self.case_a.id}/citing_laws/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["count"], 0)

    # --- Nested actions on LawViewSet -----------------------------------

    def test_law_references_action(self):
        resp = self.client.get(f"/api/laws/{self.law_823.id}/references/")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["law_id"], self.law_823.id)
        self.assertEqual(body["total_law_references"], 1)
        self.assertEqual(body["law_references"][0]["id"], self.law_249.id)

    def test_law_citing_cases_action(self):
        resp = self.client.get(f"/api/laws/{self.law_823.id}/citing_cases/")
        self.assertEqual(resp.status_code, 200)
        ids = {r["id"] for r in resp.json()["results"]}
        self.assertIn(self.case_a.id, ids)
        self.assertIn(self.case_c.id, ids)

    def test_law_citing_laws_action_empty(self):
        resp = self.client.get(f"/api/laws/{self.law_249.id}/citing_laws/")
        self.assertEqual(resp.status_code, 200)
        # law_823 cites law_249 → 249 has 1 citing law
        self.assertEqual(resp.json()["count"], 1)
        self.assertEqual(resp.json()["results"][0]["id"], self.law_823.id)

    def test_law_citing_laws_does_not_scan_for_sibling_ids(self):
        """``citing_laws`` must resolve via the slug pair, not a sibling scan.

        The action used to expand ``(book.code, section)`` into every
        matching ``Law`` id with a case-insensitive filter:

            Law.objects.filter(book__code__iexact=…, section__iexact=…)

        ``iexact`` is unindexable, so that scanned ``laws_law`` joined to
        ``laws_lawbook`` on every request — and the resulting id list was
        then collapsed straight back to a single ``(book_slug,
        section_slug)`` pair by ``_law_to_slug_pair``, i.e. the scan was
        pure waste. Under bot load these calls reached 55s in production.

        Pin the query shape so the scan can't come back.
        """
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        with CaptureQueriesContext(connection) as ctx:
            resp = self.client.get(f"/api/laws/{self.law_249.id}/citing_laws/")

        self.assertEqual(resp.status_code, 200)
        sql = " ".join(q["sql"].lower() for q in ctx.captured_queries)
        # `iexact` compiles to LIKE (sqlite/mysql) or UPPER(...) comparisons.
        self.assertNotIn("upper(", sql)
        self.assertNotIn(" like ", sql)

    def test_law_citing_laws_resolves_across_book_revisions(self):
        """A citation recorded against an older revision is still returned.

        ``Reference`` rows pin to the ``Law`` row that existed when
        extraction ran, which may live on a superseded book revision. The
        ``(book_slug, section_slug)`` pair is stable across revisions, so
        dropping the sibling-id expansion must not lose those citations.
        """
        # Older revision of the same book, same slug, different revision_date.
        old_bgb = LawBook.objects.create(
            code="BGB",
            title="BGB",
            slug="bgb",
            latest=False,
            revision_date="2020-01-01",
            review_status="accepted",
        )
        old_249 = _make_law(old_bgb, "§ 249", "249")
        # A law citing the *old* revision's row.
        citing = _make_law(self.gg, "Artikel 2", "artikel-2")
        _attach_law_law_ref(citing, old_249, "§ 249")

        resp = self.client.get(f"/api/laws/{self.law_249.id}/citing_laws/")

        self.assertEqual(resp.status_code, 200)
        ids = {r["id"] for r in resp.json()["results"]}
        # Both the current-revision citation (law_823) and the one recorded
        # against the older revision (citing) must be present.
        self.assertIn(self.law_823.id, ids)
        self.assertIn(citing.id, ids)

    # --- Flat ReferenceViewSet ------------------------------------------

    def test_flat_filter_by_cited_by_case_id(self):
        resp = self.client.get(f"/api/references/?cited_by_case={self.case_a.id}")
        self.assertEqual(resp.status_code, 200)
        # case_a has 2 outbound refs (law + case)
        self.assertEqual(resp.json()["count"], 2)

    def test_flat_filter_by_cited_by_case_slug(self):
        resp = self.client.get(
            f"/api/references/?cited_by_case__slug={self.case_a.slug}"
        )
        self.assertEqual(resp.json()["count"], 2)

    def test_flat_filter_by_cited_by_law_book_slug_and_slug(self):
        resp = self.client.get(
            "/api/references/?cited_by_law__book__slug=bgb&cited_by_law__slug=823"
        )
        self.assertEqual(resp.status_code, 200)
        # law_823 has 1 outbound ref (to law_249)
        self.assertEqual(resp.json()["count"], 1)

    def test_flat_filter_by_cites_case_id(self):
        resp = self.client.get(f"/api/references/?cites_case={self.case_b.id}")
        self.assertEqual(resp.json()["count"], 1)

    def test_flat_filter_by_cites_law_book_slug_and_slug(self):
        resp = self.client.get(
            "/api/references/?cites_law__book__slug=bgb&cites_law__slug=823"
        )
        # Two cases cite §823 BGB
        self.assertEqual(resp.json()["count"], 2)

    def test_flat_assigned_filter(self):
        # All refs in this fixture are assigned, so unassigned=0.
        resp = self.client.get("/api/references/?assigned=false")
        self.assertEqual(resp.json()["count"], 0)
        resp = self.client.get("/api/references/?assigned=true")
        self.assertGreater(resp.json()["count"], 0)

    def test_flat_serializer_shape(self):
        resp = self.client.get(
            f"/api/references/?cited_by_case={self.case_a.id}&cites_law__slug=823"
        )
        self.assertEqual(resp.json()["count"], 1)
        ref = resp.json()["results"][0]
        # Spot-check key shape so a serialiser regression is loud.
        for field in ("id", "to", "to_hash", "case", "law", "cited_by", "marker_text"):
            self.assertIn(field, ref)
        self.assertEqual(ref["law"]["book_slug"], "bgb")

    def test_citing_cases_returns_503_on_es_outage(self):
        """``/api/laws/<id>/citing_cases/`` and
        ``/api/cases/<id>/citing_cases/`` are ES-backed; on backend
        failure they must surface a 503 (not a silent SQL fallback)
        so consumers know the data path is degraded.
        """
        from unittest.mock import patch

        try:
            from elasticsearch.exceptions import ConnectionError as ESConnectionError
        except ImportError:
            self.skipTest("elasticsearch package not installed")

        with patch(
            "oldp.apps.search.utils.citing_cases_queryset_via_es",
            side_effect=ESConnectionError("ES down"),
        ):
            resp = self.client.get(f"/api/laws/{self.law_823.id}/citing_cases/")
            self.assertEqual(resp.status_code, 503)
            resp = self.client.get(f"/api/cases/{self.case_a.id}/citing_cases/")
            self.assertEqual(resp.status_code, 503)

    def test_citing_cases_returns_retryable_503_on_es_timeout(self):
        """Timeouts must map to the ``retryable: True`` body so
        agents distinguish "wait + retry" from "give up".
        """
        from unittest.mock import patch

        try:
            from elasticsearch.exceptions import ConnectionTimeout
        except ImportError:
            self.skipTest("elasticsearch package not installed")

        with patch(
            "oldp.apps.search.utils.citing_cases_queryset_via_es",
            side_effect=ConnectionTimeout("warming up"),
        ):
            resp = self.client.get(f"/api/laws/{self.law_823.id}/citing_cases/")
            self.assertEqual(resp.status_code, 503)
            body = resp.json()
            self.assertTrue(body.get("retryable"))
            self.assertIn("hint", body)

    def test_flat_serializer_uses_prefetch_cache(self):
        """``cited_by`` / ``marker_text`` must read the prefetched
        through-table rows, not re-query per row.

        Regression test for the N+1 caused by ``.first()`` in
        ``ReferenceSerializer.get_cited_by`` / ``get_marker_text``:
        each row issued ``LIMIT 1`` queries that bypassed the
        ``ReferenceViewSet.prefetch_related`` cache, so a 25-row page
        cost 50 extra queries. The fix replaces ``.first()`` with
        ``next(iter(...all()), None)`` so the iteration hits the cache.
        """
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        # Sanity: there must be at least one reference in the fixture
        resp = self.client.get("/api/references/")
        self.assertGreater(resp.json()["count"], 0)

        with CaptureQueriesContext(connection) as ctx:
            resp = self.client.get("/api/references/?page_size=10")
        self.assertEqual(resp.status_code, 200)
        # 4 fixture refs * 2 per-row queries (.first() twice) = 8 N+1
        # queries before the fix. After the fix every reference's
        # cited_by + marker_text resolves from the prefetched cache.
        # Allow some headroom for legitimate prefetch / pagination
        # queries; 25 is well below the pre-fix watermark and well
        # above the legitimate cost (~10 queries).
        self.assertLess(
            len(ctx.captured_queries),
            25,
            msg=(
                f"Expected <25 queries for a /api/references/ list page, "
                f"got {len(ctx.captured_queries)}. The serialiser may have "
                f"reintroduced .first() in get_cited_by/get_marker_text."
            ),
        )

    # --- /api/citations/validate/ ---------------------------------------

    def test_validate_law_reference_found(self):
        resp = self.client.get("/api/citations/validate/?citation=%C2%A7+823+BGB")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertTrue(body["found"])
        self.assertEqual(body["type"], "law")

    def test_validate_file_number_not_found(self):
        resp = self.client.get(
            "/api/citations/validate/?citation=ZZ+123/99&type=file_number"
        )
        body = resp.json()
        self.assertFalse(body["found"])
        self.assertEqual(body["type"], "case")

    def test_validate_empty_citation_errors(self):
        resp = self.client.get("/api/citations/validate/?citation=")
        body = resp.json()
        self.assertIn("error", body)
