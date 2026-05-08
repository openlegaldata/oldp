import logging
from dataclasses import replace
from typing import List, Tuple

from django.db import models
from django.db.models import F, Value
from django.db.models.functions import Concat
from django.utils.text import slugify
from refex.citations import CaseCitation, Citation, LawCitation
from refex.document import Document, map_span_to_raw

from oldp.apps.cases.models import Case
from oldp.apps.laws.models import Law, LawBook
from oldp.apps.processing.errors import ProcessingError
from oldp.apps.references.models import Reference, ReferenceMarker

logger = logging.getLogger(__name__)


class BaseExtractRefs(object):
    """Shared logic for case + law reference extraction.

    Subclasses construct ``self.extractor`` (a refex
    :class:`~refex.orchestrator.CitationExtractor`) and call
    :meth:`save_citations` from their ``process()`` implementation.
    """

    marker_model = None  # type: class[ReferenceMarker]
    reference_from_content_model = None  # type: class[ReferenceFromContent]

    def bulk_delete_existing_markers(self, content) -> None:
        """Drop this content's existing markers + orphan ``Reference`` rows
        in three bulk SQL statements, skipping the per-marker
        :func:`pre_delete_reference_marker` signal.

        The legacy
        ``self.marker_model.objects.filter(referenced_by=content).delete()``
        call fires ``pre_delete`` on every marker; the signal then runs
        ``Reference.objects.filter(pk__in=instance.references.all()).delete()``
        once **per marker**. With ~50 markers per case across 300k
        cases that path was the dominant cost in the per-case query
        audit (155 of 403 queries were DELETEs from the cascade).

        Same semantic outcome, fixed cost: collect orphan-Reference
        ids, drop the through-rows in one ``DELETE``, drop the
        References in one ``DELETE``, drop the markers via
        ``_raw_delete`` so the signal is bypassed.
        """
        marker_qs = self.marker_model.objects.filter(referenced_by=content)
        through_qs = self.reference_from_content_model.objects.filter(
            marker__in=marker_qs
        )

        # Capture orphan-Reference ids before we drop the through-rows.
        # Materialise as a plain list — a sub-query lookup would
        # invalidate after the first DELETE.
        reference_ids = list(through_qs.values_list("reference_id", flat=True))

        through_qs.delete()
        if reference_ids:
            Reference.objects.filter(pk__in=reference_ids).delete()
        # ``_raw_delete`` skips both signals and cascades. Cascades are
        # irrelevant: we already removed every through-row that would
        # have cascaded. Signals are exactly what we're trying to skip.
        marker_qs._raw_delete(marker_qs.db)

    @staticmethod
    def _build_section_slug(citation: LawCitation) -> str:
        """Construct the ``Law.slug`` lookup key for a law citation.

        ``Law.slug`` is built from ``Law.section`` via Django's
        ``SlugField``, which lower-cases and hyphenates ``slugify`` input.
        For paragraph cites ("§ 823 BGB") the section column stores
        ``"§ 823"`` and the slug is ``"823"``. For Article cites
        ("Art. 1 GG") the section column stores ``"Artikel 1"`` and the
        slug is ``"artikel-1"``. Refex's ``LawCitation`` carries the
        bare number plus a ``unit`` discriminator, so we prepend
        ``"artikel "`` when ``unit == "article"`` before slugifying.
        """
        number = citation.number or ""
        if citation.unit == "article":
            return slugify(f"artikel {number}")
        return slugify(number)

    def assign_law_ref(self, citation: LawCitation, ref: Reference) -> Reference:
        """Resolve a ``LawCitation`` to a ``Law`` row and attach it to ``ref``.

        Lookup keys are built with Django's ``slugify`` (so umlauts,
        non-ASCII chars, and multi-word codes like ``ÄApprO 2002`` map
        to their stored slug ``aappro-2002`` rather than failing
        silently). ``book__latest=True`` constrains the candidate set to
        the most recent revision of each LawBook, otherwise multiple
        revisions all carry a Law with the same ``slug`` and ``.first()``
        becomes order-dependent.

        If the unit-aware slug doesn't match (e.g. refex labels a cite
        as ``article`` but the corresponding Law row stores its slug
        without the ``"artikel-"`` prefix), fall back to the bare
        slugified number to keep behavior tolerant of fixture
        inconsistencies in the corpus.
        """
        if not citation.book or not citation.number:
            raise ProcessingError("Reference data is not set")

        book_slug = slugify(citation.book)
        section_slug = self._build_section_slug(citation)

        section_slugs = [section_slug]
        if citation.unit == "article":
            # Stored Law may use the bare number ("1") rather than the
            # prefixed slug ("artikel-1") even for Article cites.
            bare = slugify(citation.number)
            if bare != section_slug:
                section_slugs.append(bare)

        first = Law.objects.filter(
            book__slug=book_slug,
            slug__in=section_slugs,
            book__latest=True,
        ).first()

        if first is None:
            # Slug lookup missed — refex may emit the verbose book name
            # ("Grundgesetz") while ``LawBook.slug`` carries the short
            # code ("gg"). Refex's bundled ``law_book_codes.txt`` keeps
            # full names; OLDP's books are slugged from their short
            # codes. Fall back to matching ``LawBook.code`` /
            # ``LawBook.title`` case-insensitively so verbose-name cites
            # still resolve.
            book_ids = list(
                LawBook.objects.filter(latest=True)
                .filter(
                    models.Q(code__iexact=citation.book)
                    | models.Q(title__iexact=citation.book)
                )
                .values_list("pk", flat=True)
            )
            if book_ids:
                first = Law.objects.filter(
                    book_id__in=book_ids,
                    slug__in=section_slugs,
                ).first()

        if first is None:
            raise ProcessingError(
                "Cannot find ref target with book=%s; section=%s; for citation=%s"
                % (book_slug, section_slug, citation)
            )
        ref.law = first
        # Stable identifiers: copy the Law row's book + section slugs across.
        # Reverse-citation queries filter on these so they survive book
        # revision turnover (the FK above pins to one specific row that
        # ages out as new revisions land).
        ref.law_book_slug = first.book.slug or ""
        ref.law_section_slug = first.slug or ""
        return ref

    def assign_case_ref(self, citation: CaseCitation, ref: Reference) -> Reference:
        """Resolve a ``CaseCitation`` to a ``Case`` row and attach it to ``ref``.

        Refex's ``citation.court`` is sometimes the short cite-form
        that lives in ``Court.code`` ("BGH") and sometimes the verbose
        form from ``Court.aliases`` ("Landgericht Köln"). Both paths
        are tried in a single OR'd query.

        Aliases match as a **complete line**, not as a substring. The
        legacy ``aliases__contains`` would match "BGH" inside "OBGH",
        which produced spurious resolutions for short codes that
        appear as a substring of an unrelated court's alias. We
        normalise the comparison by padding both sides of the aliases
        value with newlines (``\\n…\\n``) and then doing an exact-line
        ``icontains`` against ``\\n<court>\\n``.
        """
        if not citation.court or not citation.file_number:
            raise ProcessingError("Reference data is not set")

        line_target = f"\n{citation.court}\n"
        candidates = Case.objects.annotate(
            _court_aliases_padded=Concat(
                Value("\n"),
                F("court__aliases"),
                Value("\n"),
                output_field=models.TextField(),
            )
        ).filter(
            models.Q(court__code__iexact=citation.court)
            | models.Q(_court_aliases_padded__icontains=line_target),
            file_number=citation.file_number,
        )

        first = candidates.first()
        if first is None:
            raise ProcessingError(
                "Cannot find ref target with court=%s; file_number=%s; for citation=%s"
                % (citation.court, citation.file_number, citation)
            )
        ref.case = first
        return ref

    @staticmethod
    def _group_by_span(citations: List[Citation]):
        """Yield (span_key, [citations]) groups, preserving original order.

        Co-located citations from one enumeration marker share an
        identical ``(start, end)`` span and are merged into a single
        group so the caller can persist them under one ``ReferenceMarker``
        with N attached ``Reference`` rows.
        """
        groups = {}
        order = []
        for citation in citations:
            if citation.kind != "full":
                continue
            key = (citation.span.start, citation.span.end)
            if key not in groups:
                groups[key] = []
                order.append(key)
            groups[key].append(citation)
        for key in order:
            yield key, groups[key]

    @staticmethod
    def _expand_range(citation: Citation) -> List[Citation]:
        """Expand a numeric ``range_end`` on a LawCitation into one citation per integer.

        Preserves the legacy convention where "§§ 12-14 BGB" produced three
        ``Reference`` rows (12, 13, 14). Citations with non-integer bounds
        (e.g. "§§ 12a-14b") are returned unchanged — extending the range
        across letter suffixes would be a guess, not a faithful
        reproduction of legacy behavior.
        """
        if not isinstance(citation, LawCitation) or not citation.range_end:
            return [citation]
        try:
            start_n = int(citation.number)
            end_n = int(citation.range_end)
        except (TypeError, ValueError):
            return [citation]
        if end_n <= start_n:
            return [citation]
        return [
            replace(citation, number=str(n), range_end=None)
            for n in range(start_n, end_n + 1)
        ]

    # Sentinel marking a cache entry where the lookup failed. Treated
    # the same as a fresh ``ProcessingError`` on cache hit so we don't
    # silently repeat the slow fallback paths on repeat misses inside
    # one ``save_citations`` invocation.
    _LOOKUP_FAILED = object()

    def _assign_law_cached(
        self, citation: LawCitation, ref: Reference, cache: dict
    ) -> Reference:
        """Cached wrapper around :meth:`assign_law_ref`.

        Cites repeat heavily inside one document (a case typically
        cites the same handful of sections N times). The lookup itself
        does up to two index hits on ``Law`` plus a verbose-name
        fallback through ``LawBook``; caching the result by
        ``(book_slug, section_slug)`` collapses those repeat lookups
        to a single SELECT per unique target.
        """
        book_slug = slugify(citation.book) if citation.book else ""
        section_slug = self._build_section_slug(citation)
        key = (book_slug, section_slug)
        if key in cache:
            cached = cache[key]
            if cached is self._LOOKUP_FAILED:
                raise ProcessingError(
                    "Cannot find ref target with book=%s; section=%s; for citation=%s"
                    % (book_slug, section_slug, citation)
                )
            ref.law, ref.law_book_slug, ref.law_section_slug = cached
            return ref
        try:
            ref = self.assign_law_ref(citation, ref)
        except ProcessingError:
            cache[key] = self._LOOKUP_FAILED
            raise
        cache[key] = (ref.law, ref.law_book_slug, ref.law_section_slug)
        return ref

    def _assign_case_cached(
        self, citation: CaseCitation, ref: Reference, cache: dict
    ) -> Reference:
        """Cached wrapper around :meth:`assign_case_ref`.

        ``assign_case_ref``'s ``Concat``-padded alias match is cheap
        per call but still touches ``cases_case`` + the ``Court``
        alias scan; for cases that cite the same precedent multiple
        times we save those repeat scans by keying the cache on the
        cite-side ``(court, file_number)``.
        """
        key = (citation.court or "", citation.file_number or "")
        if key in cache:
            cached = cache[key]
            if cached is self._LOOKUP_FAILED:
                raise ProcessingError(
                    "Cannot find ref target with court=%s; file_number=%s; for citation=%s"
                    % (citation.court, citation.file_number, citation)
                )
            ref.case = cached
            return ref
        try:
            ref = self.assign_case_ref(citation, ref)
        except ProcessingError:
            cache[key] = self._LOOKUP_FAILED
            raise
        cache[key] = ref.case
        return ref

    def save_citations(
        self,
        document: Document,
        citations: List[Citation],
        referenced_by,
        assign_references=True,
    ) -> Tuple[List[ReferenceMarker], List[Reference]]:
        """Persist typed citations as marker + Reference rows.

        Citations sharing an identical span — enumeration markers like
        "§§ 3, 3b AsylG" emit one ``LawCitation`` per section, all
        sharing the marker's span — are grouped into a single
        ``ReferenceMarker`` with N attached ``Reference`` rows, preserving
        the legacy 1:N marker→ref shape that ``insert_markers`` and the
        case-detail rendering rely on.

        Range citations (``range_end`` set) are expanded into one
        ``Reference`` per integer in the range, attached to the same
        marker.

        Short-form citations (``kind != "full"``) are skipped: refex
        resolves them via prior-context inheritance, and surfacing them
        as ``Reference`` rows is a corpus-shape change handled
        separately.

        ``marker.start`` / ``marker.end`` are translated to raw-document
        coordinates via :func:`refex.document.map_span_to_raw` so
        ``insert_markers`` can slice the original ``content``. The
        persisted ``marker.text`` (and the ``Reference.to`` mirror) is
        the **plain-text** projection of the citation, not
        ``case.content[raw.start:raw.end]``: when a citation sits inside
        nested HTML wrappers (e.g. Wolters Kluwer RDFa ``<span>`` blocks
        wrapping each section), the raw slice can balloon to >1KB of
        markup while the actual cite is ~20 chars. The references panel,
        the search-fallback link, and the to-hash grouping all want the
        clean form.

        Writes are batched: one ``bulk_create`` per ``Marker`` set,
        one per ``Reference`` set, one per through-row set. Total per
        case: 3 ``INSERT`` statements regardless of citation count.
        ``Reference.save`` is bypassed by ``bulk_create``, so the
        slug-pair invariant lives entirely on
        :meth:`assign_law_ref` (which sets ``law_book_slug`` and
        ``law_section_slug`` explicitly before this method touches
        them).
        """
        # Per-case lookup caches. Allocated fresh on each invocation so
        # entries don't leak across cases and we don't have to worry
        # about Law/Case rows changing under us between calls.
        law_cache: dict = {}
        case_cache: dict = {}

        # Phase 1 — build markers in memory + remember the citation
        # group attached to each so we can build References after the
        # marker bulk_create gives us PKs.
        pending_markers: List[ReferenceMarker] = []
        pending_groups: List[List[Citation]] = []
        for _span_key, group in self._group_by_span(citations):
            if not group:
                continue
            plain_span = group[0].span
            raw_span = map_span_to_raw(plain_span, document)
            pending_markers.append(
                self.marker_model(
                    referenced_by=referenced_by,
                    text=plain_span.text,
                    start=raw_span.start,
                    end=raw_span.end,
                )
            )
            pending_groups.append(group)

        if not pending_markers:
            return [], []

        # Phase 2 — bulk_create markers; PKs come back populated on
        # MariaDB 10.5+ / MySQL 8.0.21+ (RETURNING) which is what OLDP
        # ships, and on every supported PostgreSQL.
        markers = self.marker_model.objects.bulk_create(pending_markers)

        # Phase 3 — assign + build Reference rows in memory, paired
        # with the marker each one belongs to. Failed assignments are
        # logged + counted but still produce a Reference row so the
        # cite remains visible in the references panel as an
        # unresolved entry.
        pending_refs: List[Reference] = []
        ref_to_marker: List[ReferenceMarker] = []
        error_counter = 0
        success_counter = 0
        for marker, group in zip(markers, pending_groups):
            for citation in group:
                for sub_citation in self._expand_range(citation):
                    ref = Reference(to=marker.text)
                    if assign_references:
                        try:
                            if isinstance(sub_citation, LawCitation):
                                ref = self._assign_law_cached(
                                    sub_citation, ref, law_cache
                                )
                            elif isinstance(sub_citation, CaseCitation):
                                ref = self._assign_case_cached(
                                    sub_citation, ref, case_cache
                                )
                            else:
                                raise ProcessingError(
                                    "Unsupported citation type: %s" % type(sub_citation)
                                )
                            success_counter += 1
                        except ProcessingError:
                            # Unresolved cites are the common case
                            # (most prod cites target laws not in the
                            # local corpus); the per-content-item
                            # aggregate below is the operator-facing
                            # summary. We deliberately don't emit
                            # per-cite logs here — even at DEBUG the
                            # format + dual-handler flush dominated
                            # save_citations wall time during the
                            # 300k-case backfill profile.
                            error_counter += 1
                    ref.set_to_hash()
                    pending_refs.append(ref)
                    ref_to_marker.append(marker)

        # Phase 4 — bulk_create Reference rows.
        saved_refs = Reference.objects.bulk_create(pending_refs) if pending_refs else []

        # Phase 5 — bulk_create the through-rows, pairing each ref
        # with its marker.
        if saved_refs:
            self.reference_from_content_model.objects.bulk_create(
                [
                    self.reference_from_content_model(reference=ref, marker=marker)
                    for ref, marker in zip(saved_refs, ref_to_marker)
                ]
            )

        total = success_counter + error_counter
        if total > 0 and error_counter / total > 0.5:
            # More than half of refs failed to assign — surface as a single
            # ERROR per content item instead of one per ref (reduces noise
            # while still flagging cases that need triage).
            logger.error(
                "References: saved=%i; errors=%i (%.0f%% failed) for %s",
                success_counter,
                error_counter,
                100 * error_counter / total,
                referenced_by,
            )
        else:
            logger.debug(
                "References: saved=%i; errors=%i" % (success_counter, error_counter)
            )

        return list(markers), list(saved_refs)
