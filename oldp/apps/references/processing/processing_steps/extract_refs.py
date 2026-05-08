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
        """
        saved_markers: List[ReferenceMarker] = []
        saved_refs: List[Reference] = []

        error_counter = 0
        success_counter = 0

        for span_key, group in self._group_by_span(citations):
            if not group:
                continue

            plain_span = group[0].span
            raw_span = map_span_to_raw(plain_span, document)
            marker = self.marker_model(
                referenced_by=referenced_by,
                text=plain_span.text,
                start=raw_span.start,
                end=raw_span.end,
            )
            marker.save()

            for citation in group:
                for sub_citation in self._expand_range(citation):
                    ref = Reference(to=plain_span.text)

                    if assign_references:
                        try:
                            if isinstance(sub_citation, LawCitation):
                                ref = self.assign_law_ref(sub_citation, ref)
                            elif isinstance(sub_citation, CaseCitation):
                                ref = self.assign_case_ref(sub_citation, ref)
                            else:
                                raise ProcessingError(
                                    "Unsupported citation type: %s" % type(sub_citation)
                                )
                            success_counter += 1
                        except ProcessingError as e:
                            logger.warning(e)
                            error_counter += 1

                    ref.set_to_hash()
                    ref.save()

                    self.reference_from_content_model(
                        reference=ref, marker=marker
                    ).save()

                    saved_refs.append(ref)

            saved_markers.append(marker)

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

        return saved_markers, saved_refs
