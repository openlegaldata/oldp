import logging
from dataclasses import replace
from typing import List, Tuple

from refex.citations import CaseCitation, Citation, LawCitation
from refex.document import Document, map_span_to_raw

from oldp.apps.cases.models import Case
from oldp.apps.laws.models import Law
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
    def _clean_book(book):
        # Mirrors the legacy ``LawRefMixin.clean_book`` normalization so the
        # DB lookup against ``LawBook.slug`` keeps matching while we sit on
        # the migration. Replaced by ``slugify`` in a follow-up commit.
        if book is None:
            return None
        return book.strip().lower()

    @staticmethod
    def _clean_section(section):
        if section is None:
            return None
        return section.replace(" ", "").lower()

    def assign_law_ref(self, citation: LawCitation, ref: Reference) -> Reference:
        """Find the corresponding ``Law`` row for a law citation."""
        if not citation.book or not citation.number:
            raise ProcessingError("Reference data is not set")

        book = self._clean_book(citation.book)
        section = self._clean_section(citation.number)

        candidates = Law.objects.filter(book__slug=book, slug=section)

        first = candidates.first()
        if first is None:
            raise ProcessingError(
                "Cannot find ref target with book=%s; section=%s; for citation=%s"
                % (book, section, citation)
            )
        ref.law = first
        return ref

    def assign_case_ref(self, citation: CaseCitation, ref: Reference) -> Reference:
        """Find the corresponding ``Case`` row for a case citation."""
        if not citation.court or not citation.file_number:
            raise ProcessingError("Reference data is not set")

        candidates = Case.objects.filter(
            court__aliases__contains=citation.court,
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

        Marker offsets are translated back to raw-document coordinates
        via :func:`refex.document.map_span_to_raw` so that
        ``insert_markers`` can slice the original ``content`` correctly.
        """
        saved_markers: List[ReferenceMarker] = []
        saved_refs: List[Reference] = []

        error_counter = 0
        success_counter = 0

        for span_key, group in self._group_by_span(citations):
            if not group:
                continue

            raw_span = map_span_to_raw(group[0].span, document)
            marker = self.marker_model(
                referenced_by=referenced_by,
                text=raw_span.text,
                start=raw_span.start,
                end=raw_span.end,
            )
            marker.save()

            for citation in group:
                for sub_citation in self._expand_range(citation):
                    ref = Reference(to=raw_span.text)

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
