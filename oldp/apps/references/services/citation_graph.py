"""Citation graph traversal helpers.

Forward + reverse lookups across the citation graph. MCP tools and REST
endpoints both call into this module so query/serialization logic stays
single-sourced.

Functions that return response-ready payloads (``case_forward_references``,
``law_forward_references``) yield dicts. Functions that need to be
paginated by the caller return ``QuerySet``s — REST hands them to DRF's
paginator, MCP tools take a slice.
"""

from __future__ import annotations

import datetime
from typing import Iterable

from django.db.models import QuerySet

from oldp.apps.cases.mcp import exclude_future_dated_cases
from oldp.apps.cases.models import Case
from oldp.apps.laws.models import Law, LawBook
from oldp.apps.references.models import (
    CaseReferenceMarker,
    LawReferenceMarker,
)
from oldp.apps.references.services.citation_lookup import section_variants

CITATION_NOTE = (
    "References are automatically extracted and may be incomplete. "
    "Verify critical citations against the full text."
)


# --- Serialization helpers ----------------------------------------------


def serialize_case_summary(case: Case) -> dict:
    """Compact case representation used by graph endpoints + MCP tools."""
    return {
        "id": case.id,
        "slug": case.slug,
        "file_number": case.file_number,
        "date": str(case.date) if case.date else None,
        "court": case.court.name if case.court else None,
        "type": case.type,
    }


def serialize_law_summary(law: Law) -> dict:
    """Compact law representation used by graph endpoints + MCP tools."""
    book = law.book if law.book_id else None
    return {
        "id": law.id,
        "book_code": book.code if book else "",
        "book_slug": book.slug if book else "",
        "section": law.section,
        "slug": law.slug,
        "title": law.title,
    }


# --- Forward references (what does X cite?) -----------------------------


def _walk_forward_references(markers, *, marker_text_field: str = "text"):
    """Iterate (kind, target_dict, marker_text) over a marker queryset.

    Shared between ``case_forward_references`` and
    ``law_forward_references``: both walk the same shape of marker
    rows, differing only in the source content type. Yields ``("law",
    dict, marker_text)`` and ``("case", dict, marker_text)`` tuples.
    """
    seen_law_ids: set[int] = set()
    seen_case_ids: set[int] = set()
    for marker in markers:
        for ref in marker.references.all():
            if ref.law_id and ref.law_id not in seen_law_ids:
                seen_law_ids.add(ref.law_id)
                if ref.law is not None:
                    target = serialize_law_summary(ref.law)
                    target["marker_text"] = getattr(marker, marker_text_field)
                    yield ("law", target)
            if ref.case_id and ref.case_id not in seen_case_ids:
                seen_case_ids.add(ref.case_id)
                if ref.case is not None:
                    target = {
                        "id": ref.case.id,
                        "slug": ref.case.slug,
                        "file_number": ref.case.file_number,
                        "date": str(ref.case.date) if ref.case.date else None,
                        "marker_text": getattr(marker, marker_text_field),
                    }
                    yield ("case", target)


def _forward_references_payload(
    *,
    source_id: int,
    source_label: str,
    source_value,
    markers,
    extracted_at,
) -> dict:
    """Bundle the walked references into the response shape."""
    law_refs = []
    case_refs = []
    for kind, target in _walk_forward_references(markers):
        if kind == "law":
            law_refs.append(target)
        else:
            case_refs.append(target)
    return {
        f"{source_label}_id": source_id,
        f"{source_label}_file_number"
        if source_label == "case"
        else f"{source_label}_section": source_value,
        "total_law_references": len(law_refs),
        "total_case_references": len(case_refs),
        "law_references": law_refs,
        "case_references": case_refs,
        "references_extracted_at": (extracted_at.isoformat() if extracted_at else None),
        "note": CITATION_NOTE,
    }


def case_forward_references(case: Case) -> dict:
    """All laws + cases that ``case`` cites in its body.

    Mirrors the shape of the MCP ``get_case_references`` tool. Uses
    prefetch so target rows resolve in a constant number of queries.
    """
    markers = CaseReferenceMarker.objects.filter(referenced_by=case).prefetch_related(
        "references",
        "references__law",
        "references__law__book",
        "references__case",
    )
    return _forward_references_payload(
        source_id=case.id,
        source_label="case",
        source_value=case.file_number,
        markers=markers,
        extracted_at=case.references_extracted_at,
    )


def law_forward_references(law: Law) -> dict:
    """All laws + cases that ``law`` cites in its body.

    Same shape as :func:`case_forward_references` but rooted on a
    ``Law`` and walking ``LawReferenceMarker`` rows. Laws can in
    principle cite both other laws and cases; in practice they
    overwhelmingly cite laws (intra-book ``§ N`` cross-references).
    """
    markers = LawReferenceMarker.objects.filter(referenced_by=law).prefetch_related(
        "references",
        "references__law",
        "references__law__book",
        "references__case",
    )
    return _forward_references_payload(
        source_id=law.id,
        source_label="law",
        source_value=law.section,
        markers=markers,
        extracted_at=law.references_extracted_at,
    )


# --- Reverse references (who cites X?) -----------------------------------


def _normalize_law_target(law_or_ids: Law | int | Iterable[int]) -> list[int]:
    """Coerce a Law / id / id-iterable into a list of law ids.

    Reverse-citation queries hit ``Reference.law_id__in=…`` so all
    revisions of the same statute section can be resolved together —
    ``Reference.law_id`` is pinned to the specific ``Law`` row that
    existed when extraction ran, which may be on an older book
    revision.
    """
    if isinstance(law_or_ids, Law):
        return [law_or_ids.id]
    if isinstance(law_or_ids, int):
        return [law_or_ids]
    return list(law_or_ids)


def citing_cases_for_case(case: Case) -> QuerySet[Case]:
    """``Case`` queryset of cases whose body cites ``case``."""
    return (
        exclude_future_dated_cases(
            Case.objects.filter(
                casereferencemarker__references__case_id=case.id,
                review_status="accepted",
            )
        )
        .select_related("court")
        .order_by("-date")
        .distinct()
    )


def citing_cases_for_law(law_or_ids: Law | int | Iterable[int]) -> QuerySet[Case]:
    """``Case`` queryset of cases whose body cites the given law section.

    Accepts a single ``Law``, a single id, or a list of ids (for
    cross-revision lookups via :func:`resolve_law_section`).
    """
    law_ids = _normalize_law_target(law_or_ids)
    return (
        exclude_future_dated_cases(
            Case.objects.filter(
                casereferencemarker__referencefromcase__reference__law_id__in=law_ids,
                review_status="accepted",
            )
        )
        .select_related("court")
        .order_by("-date")
        .distinct()
    )


def citing_laws_for_case(case: Case) -> QuerySet[Law]:
    """``Law`` queryset of laws whose body cites ``case``.

    Symmetric to :func:`citing_cases_for_case`. Rare in practice — laws
    overwhelmingly cite other laws, not cases — but exposed for
    symmetry and to support analytical queries against the flat
    ``/api/references/`` resource.
    """
    return (
        Law.objects.filter(
            lawreferencemarker__references__case_id=case.id,
            review_status="accepted",
            book__latest=True,
        )
        .select_related("book")
        .order_by("book__order", "order")
        .distinct()
    )


def citing_laws_for_law(law_or_ids: Law | int | Iterable[int]) -> QuerySet[Law]:
    """``Law`` queryset of laws whose body cites the given law section."""
    law_ids = _normalize_law_target(law_or_ids)
    return (
        Law.objects.filter(
            lawreferencemarker__referencefromlaw__reference__law_id__in=law_ids,
            review_status="accepted",
            book__latest=True,
        )
        .select_related("book")
        .order_by("book__order", "order")
        .distinct()
    )


# --- Slug → law-row resolution ------------------------------------------


def resolve_law_section(book_code: str, section: str) -> tuple[Law | None, list[int]]:
    """Resolve ``(book_code, section)`` to a primary ``Law`` + all matching ids.

    Aggregates matching ``Law`` rows across **all revisions** of the
    book: ``Reference.law_id`` pins references to the specific row that
    existed when extraction ran, which may be on an older revision. If
    we only checked the latest revision we'd miss every citation
    extracted before the most recent revision was added.

    Returns:
        ``(primary, [law.id, …])`` where ``primary`` is the canonical
        row to surface in the response (latest revision preferred),
        and the id list is the full cross-revision set for graph
        queries. Returns ``(None, [])`` when no match.
    """
    if not LawBook.objects.filter(
        code__iexact=book_code, review_status="accepted"
    ).exists():
        return None, []

    laws_qs = Law.objects.filter(
        book__code__iexact=book_code, review_status="accepted"
    ).select_related("book")

    matched: list[Law] = []
    for variant in section_variants(section):
        matched = list(laws_qs.filter(section__iexact=variant))
        if matched:
            break

    if not matched:
        return None, []

    # Prefer the row whose book is marked latest; otherwise pick the most
    # recent revision_date.
    primary = next(
        (law for law in matched if law.book.latest),
        max(matched, key=lambda law: law.book.revision_date or datetime.date.min),
    )
    return primary, [law.id for law in matched]


__all__ = [
    "CITATION_NOTE",
    "case_forward_references",
    "citing_cases_for_case",
    "citing_cases_for_law",
    "citing_laws_for_case",
    "citing_laws_for_law",
    "law_forward_references",
    "resolve_law_section",
    "serialize_case_summary",
    "serialize_law_summary",
]
