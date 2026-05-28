"""Re-resolve previously-unassigned ``Reference`` rows.

Why this exists
---------------
References are populated during case ingestion: refex extracts citation
markers from ``case.content`` and the per-cite ``Reference`` row is saved
with the matching ``Law`` FK (and ``law_book_slug`` / ``law_section_slug``
columns) if one exists.

If the target ``LawBook`` did not yet exist when the case was ingested,
the marker still gets saved (refex recognises the citation shape on its
own) but the ``Reference`` row ends up with ``law_id IS NULL``. Once the
book is later ingested, the historical rows do not automatically refresh
themselves — the assignment step only runs at extraction time.

That happens whenever we add a new ``LawBook`` to an established corpus:
ingesting DSGVO + the other EU regulations is the concrete trigger this
command was written for. Without backfilling, ``get_cases_for_law`` and
``cited_by_case``-style queries return zero matches for these new books
even though the markers + references are sitting there.

What it does
------------
Targets ``CaseReferenceMarker`` rows whose text mentions a configurable
set of book codes (defaults to the EU bundle ingested via
``oldp-ingestor``). For each marker:

  1. Re-parses ``marker.text`` with the same ``RegexLawExtractor`` used at
     extraction time. The parse output is grouped + expanded the same way
     ``save_citations`` does so we can pair citations 1:1 with the
     ``Reference`` rows the original run created (ordered by PK).

  2. When the citation list length matches the attached-ref list length,
     walks the pairs and calls ``BaseExtractRefs.assign_law_ref`` on
     each ``ref.law_id IS NULL`` row whose citation now resolves to a
     present-in-DB book.

  3. Skips markers whose count drifts (refex output today differs from
     the count at original-ingest time) — pairing in that case would
     mis-assign sections to the wrong refs, and the cost of leaving them
     for a manual pass is small.

This is intentionally not the legacy ``assign_references`` command: that
one reads ``Reference.to`` as JSON, which the modern (refex-based)
extraction pipeline no longer produces.
"""

from __future__ import annotations

import logging
from typing import List

from django.core.management import BaseCommand
from refex.document import make_document
from refex.engines.regex import RegexLawExtractor
from refex.orchestrator import CitationExtractor

from oldp.apps.processing.errors import ProcessingError
from oldp.apps.references.models import (
    CaseReferenceMarker,
    Reference,
    ReferenceFromCase,
)
from oldp.apps.references.processing.processing_steps.extract_refs import (
    BaseExtractRefs,
)

logger = logging.getLogger(__name__)


DEFAULT_BOOK_CODES = [
    "DSGVO",
    "DSA",
    "DMA",
    "KI-VO",
    "eIDAS-VO",
    "JI-RL",
    "Brüssel-Ia-VO",
    "Rom-I-VO",
    "Rom-II-VO",
    "DSM-RL",
]


class _Resolver(BaseExtractRefs):
    """Concrete ``BaseExtractRefs`` solely so we can call
    :meth:`assign_law_ref` and :meth:`_expand_range`. We never touch
    ``save_citations`` here — this command updates existing rows in
    place rather than re-running the extraction pipeline.
    """

    marker_model = CaseReferenceMarker
    reference_from_content_model = ReferenceFromCase


class Command(BaseCommand):
    help = (
        "Re-resolve Reference rows whose target LawBook did not exist at "
        "extraction time (e.g. DSGVO and other EU regulations ingested later)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--book",
            action="append",
            default=None,
            help=(
                "Filter to markers whose text mentions this book code. "
                "Repeatable. Defaults to the EU bundle: "
                f"{', '.join(DEFAULT_BOOK_CODES)}."
            ),
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=0,
            help="Process at most this many markers (0 = no limit).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            default=False,
            help="Walk markers and parse citations but do not write to DB.",
        )

    def handle(self, *args, **options):
        from django.db.models import Q

        book_codes = options["book"] or DEFAULT_BOOK_CODES
        book_codes_lower = {b.lower() for b in book_codes}

        marker_filter = Q()
        for code in book_codes:
            marker_filter |= Q(text__icontains=code)

        markers_qs = CaseReferenceMarker.objects.filter(marker_filter).order_by("pk")
        if options["limit"] > 0:
            markers_qs = markers_qs[: options["limit"]]

        # One ``CitationExtractor`` for the whole run; refex engines are
        # cheap to construct but caching avoids per-marker setup overhead.
        engine = RegexLawExtractor()
        extractor = CitationExtractor(engines=[engine])
        resolver = _Resolver()

        scanned = 0
        resolved = 0
        skipped_mismatch = 0
        resolve_failed = 0
        markers_with_changes = 0

        for marker in markers_qs.iterator():
            scanned += 1
            citations = self._parse_marker(marker.text, extractor, resolver)
            refs = list(
                Reference.objects.filter(referencefromcase__marker=marker).order_by(
                    "pk"
                )
            )

            if len(citations) != len(refs):
                skipped_mismatch += 1
                logger.debug(
                    "skip marker=%s count_mismatch citations=%d refs=%d text=%r",
                    marker.pk,
                    len(citations),
                    len(refs),
                    marker.text,
                )
                continue

            marker_changed = False
            for citation, ref in zip(citations, refs):
                if ref.law_id is not None:
                    continue
                if (citation.book or "").lower() not in book_codes_lower:
                    # Marker mentioned an EU book somewhere, but this
                    # particular citation targets a different (likely
                    # unresolved-from-elsewhere) book. Leave it alone.
                    continue
                try:
                    resolver.assign_law_ref(citation, ref)
                except ProcessingError as exc:
                    resolve_failed += 1
                    logger.debug(
                        "assign_law_ref failed citation=%s err=%s", citation, exc
                    )
                    continue

                ref.set_to_hash()
                if not options["dry_run"]:
                    ref.save()
                resolved += 1
                marker_changed = True

            if marker_changed:
                markers_with_changes += 1

        self.stdout.write(f"Markers scanned:        {scanned}")
        self.stdout.write(f"Markers with changes:   {markers_with_changes}")
        self.stdout.write(f"References resolved:    {resolved}")
        self.stdout.write(f"Resolve failures:       {resolve_failed}")
        self.stdout.write(f"Markers skipped (count mismatch): {skipped_mismatch}")
        if options["dry_run"]:
            self.stdout.write("DRY-RUN: no rows were written.")

    @staticmethod
    def _parse_marker(text: str, extractor, resolver) -> List:
        """Reproduce the same citation list that ``save_citations`` would
        have produced for ``marker.text`` at ingest time.

        Specifically: filter to ``kind == "full"`` (short-form cites are
        not persisted as ``Reference`` rows) and apply
        :meth:`_expand_range` so e.g. ``§§ 12-14`` expands into three
        per-section entries — that is exactly how the original extraction
        sized the ``Reference`` row list, and our pairing depends on
        mirroring it byte-for-byte.
        """
        doc = make_document(text, fmt="text")
        result = extractor.extract(doc)
        citations: List = []
        for citation in result.citations:
            if citation.kind != "full":
                continue
            citations.extend(resolver._expand_range(citation))
        return citations
