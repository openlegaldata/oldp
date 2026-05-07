from django.test import TestCase, TransactionTestCase, tag
from refex.citations import LawCitation, Span

from oldp.apps.cases.models import Case
from oldp.apps.cases.processing.processing_steps.extract_refs import (
    ProcessingStep as ExtractRefsStep,
)
from oldp.apps.laws.models import Law, LawBook
from oldp.apps.processing.errors import ProcessingError
from oldp.apps.references.models import Reference
from oldp.apps.references.processing.processing_steps.extract_refs import (
    BaseExtractRefs,
)


@tag("processing")
class ExtractReferencesTestCase(TransactionTestCase):
    """./manage.py dumpdata references --output refs.json"""

    fixtures = [
        "courts/default.json",
        "cases/case_with_references.json",
        "laws/empty_bgb.json",
    ]

    def test_extract_law_refs_from_case(self):
        case = Case.objects.get(pk=1888)

        # law_book_codes left unset — the extractor uses the bundled
        # legal-reference-extraction code list (~1947 codes + unit hints).
        step = ExtractRefsStep(
            law_refs=True,
            case_refs=False,
            assign_refs=True,
        )

        processed = step.process(case)

        # Counts updated for legal-reference-extraction 0.5.0, which adds
        # `Art.` / Grundgesetz citation patterns (CHANGELOG Stream E).
        # The fixture now yields 5 additional Art. GG markers for 3 new
        # target groups (GG/2, GG/14, GG/34) compared to v0.4.x.
        self.assertEqual(33, len(processed.get_references()))

        groups = processed.get_grouped_references()

        self.assertEqual(16, len(groups))


@tag("processing")
class ExtractTableReferencesTestCase(TransactionTestCase):
    """Pin extraction of citations inside HTML tables.

    Production case 183007 surfaces references inside ``<table>``
    structures (one citation per ``<td>``). Pre-migration the legacy
    ``RefExtractor`` ran on the raw HTML as plain text and its naïve
    tokenisation didn't reach into table cells, so extraction yielded
    zero markers for these decisions.

    Post-migration ``CitationExtractor`` with ``fmt="html"`` lets refex
    normalise block-level structure (``<tr>`` is in the block-tag set)
    and the citations surface. This test pins both: (a) extraction
    finds the table-bound cites, and (b) the marker offsets point back
    into the original HTML correctly — i.e. ``map_span_to_raw`` is
    being applied. The slicing canary at the bottom is the load-bearing
    assertion: if anyone forgets to translate spans, the marker would
    point inside an HTML tag and ``insert_markers`` would emit broken
    markup on the case-detail view.
    """

    fixtures = [
        "courts/default.json",
        "cases/case_with_table_references.json",
        "laws/empty_bgb.json",
    ]

    def test_extracts_citations_inside_table_cells(self):
        case = Case.objects.get(pk=183007)
        step = ExtractRefsStep(law_refs=True, case_refs=False, assign_refs=False)

        processed = step.process(case)
        markers = list(processed.get_reference_markers())
        marker_texts = sorted(m.text for m in markers)

        # Bare-minimum guard: the regression that motivated the
        # migration is "table-shape decisions yielded zero markers".
        self.assertGreater(
            len(markers),
            0,
            "Table-formatted citations did not surface — refex's HTML "
            "normalizer is no longer descending into <tr>/<td>, or "
            "fmt='html' is not being passed through.",
        )

        # Specific BGB sections that live inside <td> cells.
        for expected in ("§ 823 BGB", "§ 826 BGB", "§ 280 BGB"):
            self.assertIn(
                expected,
                marker_texts,
                f"Expected table-cell cite {expected!r}; got {marker_texts}",
            )

        # Inline cite outside the table — sanity check that the table
        # path didn't displace the regular flow.
        self.assertIn("§ 249 BGB", marker_texts)

        # Slicing canary — proves map_span_to_raw is being applied.
        # If marker offsets were left in normalized-text coordinates,
        # this slice would land inside an HTML tag and produce broken
        # output when insert_markers wraps it for the case-detail view.
        for marker in markers:
            self.assertEqual(
                case.content[marker.start : marker.end],
                marker.text,
                f"Marker offsets out of sync with raw content: "
                f"content[{marker.start}:{marker.end}]="
                f"{case.content[marker.start : marker.end]!r} "
                f"≠ marker.text={marker.text!r}. "
                "Most likely map_span_to_raw is not being applied "
                "before persisting the marker.",
            )


@tag("processing")
class AssignLawRefTestCase(TestCase):
    """Direct unit tests for ``BaseExtractRefs.assign_law_ref``.

    The legacy assignment used a bare ``str.lower`` / ``replace(' ', '')``
    normalization that silently failed for non-ASCII codes
    (``ÄApprO 2002`` ≠ ``aappro-2002``) and for Grundgesetz Articles
    (refex emits ``number="1"`` for ``Art. 1 GG`` but the stored
    ``Law.slug`` is ``"artikel-1"``). It also missed the
    ``book__latest=True`` filter, so multiple revisions of one book
    matched the same ``(slug, slug)`` and ``.first()`` returned a
    non-deterministic stale revision.

    These tests pin the corrected behaviour: Django ``slugify``,
    unit-aware section slug, latest-revision filter, with a bare-slug
    fallback for Articles whose stored slug skips the ``"artikel-"``
    prefix.
    """

    def setUp(self):
        # Resolver borrows BaseExtractRefs directly; no engines needed.
        class _Resolver(BaseExtractRefs):
            pass

        self.resolver = _Resolver()

    def _make_book(self, *, code, slug, latest=True, revision_date):
        return LawBook.objects.create(
            code=code,
            title=code,
            slug=slug,
            latest=latest,
            revision_date=revision_date,
        )

    def _make_law(self, *, book, section, slug):
        return Law.objects.create(
            book=book,
            section=section,
            slug=slug,
            content="",
            title="",
        )

    def test_resolves_paragraph_citation(self):
        book = self._make_book(code="BGB", slug="bgb", revision_date="2024-01-01")
        law = self._make_law(book=book, section="§ 823", slug="823")

        citation = LawCitation(
            span=Span(0, 9, "§ 823 BGB"),
            book="BGB",
            number="823",
            unit="paragraph",
        )
        ref = self.resolver.assign_law_ref(citation, Reference(to="§ 823 BGB"))

        self.assertEqual(ref.law_id, law.id)

    def test_resolves_grundgesetz_article(self):
        """Article cite ``unit="article"`` must build slug ``artikel-N``."""
        book = self._make_book(code="GG", slug="gg", revision_date="2024-01-01")
        law = self._make_law(book=book, section="Artikel 1", slug="artikel-1")

        citation = LawCitation(
            span=Span(0, 8, "Art. 1 GG"),
            book="GG",
            number="1",
            unit="article",
        )
        ref = self.resolver.assign_law_ref(citation, Reference(to="Art. 1 GG"))

        self.assertEqual(ref.law_id, law.id)

    def test_resolves_non_ascii_book_code(self):
        """``ÄApprO 2002`` slugifies to ``aappro-2002``."""
        book = self._make_book(
            code="ÄApprO 2002", slug="aappro-2002", revision_date="2024-01-01"
        )
        law = self._make_law(book=book, section="§ 35", slug="35")

        citation = LawCitation(
            span=Span(0, 14, "§ 35 ÄApprO 2002"),
            book="ÄApprO 2002",
            number="35",
            unit="paragraph",
        )
        ref = self.resolver.assign_law_ref(citation, Reference(to="§ 35 ÄApprO 2002"))

        self.assertEqual(ref.law_id, law.id)

    def test_prefers_latest_revision(self):
        """Two revisions, both with a Law/823: only the latest must match."""
        old_book = self._make_book(
            code="BGB", slug="bgb", latest=False, revision_date="2010-01-01"
        )
        new_book = self._make_book(
            code="BGB", slug="bgb", latest=True, revision_date="2024-01-01"
        )
        self._make_law(book=old_book, section="§ 823", slug="823")
        new_law = self._make_law(book=new_book, section="§ 823", slug="823")

        citation = LawCitation(
            span=Span(0, 9, "§ 823 BGB"),
            book="BGB",
            number="823",
            unit="paragraph",
        )
        ref = self.resolver.assign_law_ref(citation, Reference(to="§ 823 BGB"))

        self.assertEqual(
            ref.law_id,
            new_law.id,
            "Resolver returned a non-latest revision; book__latest=True "
            "filter is missing or being dropped.",
        )

    def test_article_falls_back_to_bare_slug(self):
        """Refex labels a cite ``article`` but the row stores its slug bare."""
        book = self._make_book(code="GG", slug="gg", revision_date="2024-01-01")
        # Stored slug "1" rather than "artikel-1" — fixture inconsistency.
        law = self._make_law(book=book, section="Artikel 1", slug="1")

        citation = LawCitation(
            span=Span(0, 8, "Art. 1 GG"),
            book="GG",
            number="1",
            unit="article",
        )
        ref = self.resolver.assign_law_ref(citation, Reference(to="Art. 1 GG"))

        self.assertEqual(ref.law_id, law.id)

    def test_raises_when_no_match(self):
        # No Law rows at all — assignment must surface as ProcessingError so
        # save_citations can count it toward the per-doc error rate.
        citation = LawCitation(
            span=Span(0, 9, "§ 999 ZZZ"),
            book="ZZZ",
            number="999",
            unit="paragraph",
        )
        with self.assertRaises(ProcessingError):
            self.resolver.assign_law_ref(citation, Reference(to="§ 999 ZZZ"))

    def test_populates_stable_slug_pair(self):
        """``assign_law_ref`` writes the (book_slug, section_slug) pair used by
        reverse-citation queries, not just the FK."""
        book = self._make_book(code="BGB", slug="bgb", revision_date="2024-01-01")
        self._make_law(book=book, section="§ 823", slug="823")

        citation = LawCitation(
            span=Span(0, 9, "§ 823 BGB"),
            book="BGB",
            number="823",
            unit="paragraph",
        )
        ref = self.resolver.assign_law_ref(citation, Reference(to="§ 823 BGB"))

        self.assertEqual(ref.law_book_slug, "bgb")
        self.assertEqual(ref.law_section_slug, "823")

    def test_save_backfills_slugs_when_only_fk_set(self):
        """Setting ``ref.law`` directly (no extraction) still ends up with
        the slug pair populated on save — the invariant
        "law set ⇒ slugs populated" is enforced by ``Reference.save``.
        """
        book = self._make_book(code="BGB", slug="bgb", revision_date="2024-01-01")
        law = self._make_law(book=book, section="§ 823", slug="823")

        ref = Reference(law=law, to="§ 823 BGB")
        ref.set_to_hash()
        ref.save()
        ref.refresh_from_db()

        self.assertEqual(ref.law_book_slug, "bgb")
        self.assertEqual(ref.law_section_slug, "823")


@tag("processing")
class AssignCaseRefTestCase(TestCase):
    """Tests for ``BaseExtractRefs.assign_case_ref`` line-anchored alias matching."""

    def setUp(self):
        from oldp.apps.references.processing.processing_steps.extract_refs import (
            BaseExtractRefs,
        )

        class _Resolver(BaseExtractRefs):
            pass

        self.resolver = _Resolver()

    def _make_court(self, *, code: str, slug: str, aliases: str = ""):
        from oldp.apps.courts.models import Country, Court, State

        de, _ = Country.objects.get_or_create(code="DE", defaults={"name": "Germany"})
        state, _ = State.objects.get_or_create(
            pk=1,
            defaults={"name": "Test", "country": de, "slug": "test"},
        )
        return Court.objects.create(
            name=f"Court {code}",
            slug=slug,
            code=code,
            aliases=aliases,
            state=state,
            review_status="accepted",
        )

    def _make_case(self, *, court, file_number: str):
        from datetime import date

        return Case.objects.create(
            court=court,
            file_number=file_number,
            slug=f"case-{file_number.replace(' ', '-').replace('/', '-')}",
            date=date(2024, 1, 1),
            ecli=f"ECLI:DE:TEST:{file_number}",
            review_status="accepted",
        )

    def test_resolves_via_court_code(self):
        """When ``citation.court`` matches ``Court.code`` exactly, resolve
        regardless of what's in ``aliases``. BGH cites where ``aliases``
        only ships the long form ("Bundesgerichtshof") still work because
        ``Court.code="BGH"`` is checked first.
        """
        from refex.citations import CaseCitation, Span

        court = self._make_court(code="BGH", slug="bgh", aliases="Bundesgerichtshof")
        case = self._make_case(court=court, file_number="VI ZR 100/22")

        citation = CaseCitation(
            span=Span(0, 14, "BGH VI ZR 100/22"),
            court="BGH",
            file_number="VI ZR 100/22",
        )
        ref = self.resolver.assign_case_ref(citation, Reference(to="x"))
        self.assertEqual(ref.case_id, case.id)

    def test_resolves_via_aliases_exact_line(self):
        """``Court.aliases`` is newline-delimited; the cite resolves only
        when the citation's court matches a complete alias line."""
        from refex.citations import CaseCitation, Span

        court = self._make_court(
            code="LSGNRW",
            slug="lsgnrw",
            aliases="Landessozialgericht NRW\nLSG NRW\nNordrhein-Westfalen LSG",
        )
        case = self._make_case(court=court, file_number="L 2 AS 273/14")

        citation = CaseCitation(
            span=Span(0, 18, "LSG NRW L 2 AS 273/14"),
            court="LSG NRW",
            file_number="L 2 AS 273/14",
        )
        ref = self.resolver.assign_case_ref(citation, Reference(to="x"))
        self.assertEqual(ref.case_id, case.id)

    def test_does_not_match_substring_of_alias(self):
        """Regression: legacy ``aliases__contains`` would match "BGH"
        as a substring of "OBGH" or similar. The line-anchored match
        prevents that false positive.
        """
        from refex.citations import CaseCitation, Span

        # Court whose alias *contains* the substring "BGH" but isn't BGH.
        wrong_court = self._make_court(
            code="OBGH", slug="obgh", aliases="OBGH-Hannover"
        )
        self._make_case(court=wrong_court, file_number="VI ZR 100/22")

        citation = CaseCitation(
            span=Span(0, 14, "BGH VI ZR 100/22"),
            court="BGH",
            file_number="VI ZR 100/22",
        )
        # No real BGH court / case exists in this test → should raise.
        with self.assertRaises(ProcessingError):
            self.resolver.assign_case_ref(citation, Reference(to="x"))

    def test_aliases_match_when_alias_is_first_or_last_line(self):
        """Edge case: alias appears as the first / last line of the
        TextField (no leading / trailing newline). The Concat-padded
        comparison should still match.
        """
        from refex.citations import CaseCitation, Span

        court_first = self._make_court(
            code="LGK", slug="lg-koln-first", aliases="LG Köln\nLandgericht Köln"
        )
        court_last = self._make_court(
            code="OLGD",
            slug="olg-d",
            aliases="Oberlandesgericht Düsseldorf\nOLG Düsseldorf",
        )
        first_case = self._make_case(court=court_first, file_number="1 O 1/24")
        last_case = self._make_case(court=court_last, file_number="2 U 2/24")

        cite_first = CaseCitation(
            span=Span(0, 1, "LG Köln 1 O 1/24"),
            court="LG Köln",
            file_number="1 O 1/24",
        )
        cite_last = CaseCitation(
            span=Span(0, 1, "OLG Düsseldorf 2 U 2/24"),
            court="OLG Düsseldorf",
            file_number="2 U 2/24",
        )
        self.assertEqual(
            self.resolver.assign_case_ref(cite_first, Reference(to="x")).case_id,
            first_case.id,
        )
        self.assertEqual(
            self.resolver.assign_case_ref(cite_last, Reference(to="x")).case_id,
            last_case.id,
        )


@tag("processing")
class BulkDeleteExistingMarkersTestCase(TestCase):
    """``BaseExtractRefs.bulk_delete_existing_markers`` semantics + cost.

    Two invariants worth pinning so a future refactor doesn't silently
    re-introduce the per-marker pre_delete signal cascade:

    1. **Same outcome** as the legacy
       ``CaseReferenceMarker.objects.filter(...).delete()`` plus signal
       — markers gone, orphan References gone, through-rows gone.
    2. **Bounded cost**: three ``DELETE`` statements regardless of how
       many markers the content has, vs. the legacy O(N) cascade that
       ran one SELECT + one DELETE per marker.
    """

    @classmethod
    def setUpTestData(cls):
        from oldp.apps.cases.models import Case
        from oldp.apps.courts.models import Country, Court, State
        from oldp.apps.references.models import (
            CaseReferenceMarker,
            ReferenceFromCase,
        )
        from datetime import date

        de, _ = Country.objects.get_or_create(code="DE", defaults={"name": "Germany"})
        state, _ = State.objects.get_or_create(
            pk=1,
            defaults={"name": "Test", "country": de, "slug": "test"},
        )
        cls.court = Court.objects.create(
            name="Court",
            slug="t",
            code="T",
            state=state,
            review_status="accepted",
        )
        cls.case = Case.objects.create(
            court=cls.court,
            file_number="X 1/24",
            slug="x-1-24",
            date=date(2024, 1, 1),
            ecli="ECLI:DE:T:1",
            review_status="accepted",
        )

        # Build N markers, each with one Reference, attached via the
        # through-row. Pick N intentionally larger than the historical
        # bug's "one query per marker" threshold so the test would
        # have failed against the legacy cascade.
        cls.N_MARKERS = 25
        for i in range(cls.N_MARKERS):
            marker = CaseReferenceMarker.objects.create(
                referenced_by=cls.case,
                text=f"§ {i} TEST",
                start=i,
                end=i + 9,
            )
            ref = Reference.objects.create(to=f"§ {i} TEST")
            ref.set_to_hash()
            ref.save()
            ReferenceFromCase.objects.create(marker=marker, reference=ref)

    def setUp(self):
        from oldp.apps.cases.processing.processing_steps.extract_refs import (
            ProcessingStep as ExtractRefsStep,
        )

        self.step = ExtractRefsStep(law_refs=False, case_refs=False, assign_refs=False)

    def test_removes_markers_and_orphan_references(self):
        from oldp.apps.references.models import (
            CaseReferenceMarker,
            ReferenceFromCase,
        )

        self.step.bulk_delete_existing_markers(self.case)

        self.assertEqual(
            CaseReferenceMarker.objects.filter(referenced_by=self.case).count(),
            0,
        )
        self.assertEqual(
            ReferenceFromCase.objects.filter(marker__referenced_by=self.case).count(),
            0,
        )
        # Reference rows that were attached only to this case's
        # markers should be gone too — that's the cleanup the legacy
        # ``pre_delete`` signal did per-marker; we're doing it in bulk.
        self.assertEqual(Reference.objects.count(), 0)

    def test_bounded_query_count(self):
        """DELETEs stay O(1) regardless of marker count.

        We expect three explicit bulk DELETEs (through-rows,
        References, markers). Django's ``Reference.objects.delete()``
        also fires redundant cascade DELETEs on both through-tables
        (empty no-ops in practice — the through-rows were already
        gone) which is why the upper bound is 6 rather than 3. The
        load-bearing assertion is that the count **doesn't grow with
        the marker fixture size** — a regression that re-introduced
        the per-marker ``pre_delete`` signal cascade would fire one
        SELECT + one DELETE per marker, blowing through the bound.
        """
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        with CaptureQueriesContext(connection) as ctx:
            self.step.bulk_delete_existing_markers(self.case)

        delete_count = sum(
            1
            for q in ctx.captured_queries
            if q["sql"].strip().upper().startswith("DELETE")
        )
        self.assertLessEqual(
            delete_count,
            6,
            msg=(
                f"Expected at most 6 DELETE statements (3 explicit + cascade "
                f"no-ops); got {delete_count} for {self.N_MARKERS} markers. "
                f"A regression here usually means the per-marker pre_delete "
                f"signal cascade was re-introduced."
            ),
        )
