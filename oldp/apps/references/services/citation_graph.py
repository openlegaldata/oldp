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

from django.db import connection
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
    # Treat the unresolved-court placeholder (code "unknown", ~2% of cases,
    # audit A4) as null so consumers don't mistake it for a real court —
    # consistent with search_cases / search_legal (``_norm_court``).
    court = None
    if case.court_id and (case.court.code or "").strip().lower() != "unknown":
        court = case.court.name
    return {
        "id": case.id,
        "slug": case.slug,
        "file_number": case.file_number,
        "date": str(case.date) if case.date else None,
        "court": court,
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


def _law_to_slug_pair(law_or_ids: Law | int | Iterable[int]) -> tuple[str, str] | None:
    """Map a ``Law`` / id / id-iterable to a ``(book_slug, section_slug)`` pair.

    Returns ``None`` when the input is an id list spanning multiple
    sections (which has no single slug pair) — callers that pass an
    id list should typically have used :func:`resolve_law_section`
    upstream and are about to swap to the slug helpers below.
    """
    if isinstance(law_or_ids, Law):
        return law_or_ids.book.slug, law_or_ids.slug
    if isinstance(law_or_ids, int):
        law = Law.objects.select_related("book").filter(pk=law_or_ids).first()
        return (law.book.slug, law.slug) if law else None
    ids = list(law_or_ids)
    if not ids:
        return None
    pairs = set(Law.objects.filter(pk__in=ids).values_list("book__slug", "slug"))
    return pairs.pop() if len(pairs) == 1 else None


# Two query shapes were considered for the citing-side lookups:
#
#   1. Single query: ``Case.objects.filter(<JOIN reaches Reference>)`` —
#      what the original code did. MariaDB's plan was ``Using temporary;
#      Using filesort`` and the outer ``ORDER BY date DESC LIMIT N`` could
#      not be pushed through the wide JOIN. Popular sections (§ 1 KSchG,
#      § 242 BGB) ran 14-18s.
#
#   2. Two queries: materialise the citing-content ids in Python, then
#      ``Model.objects.filter(id__in=[...])`` — the literal IN list lets
#      MariaDB walk the outer table's index by sort order. § 242 BGB
#      with 17k citing-case ids returns in ~130ms.
#
# The defer on the second query matters as much as the query shape:
# without it, reading the heavy TEXT columns (raw, content, abstract)
# for the 20-row page took 12s of off-page fetches even with the fast
# plan. ``defer_fields_list_view`` is the same set the list endpoints
# already use for their primary queryset.


# The helpers below intentionally use raw SQL with STRAIGHT_JOIN (on
# MariaDB/MySQL). The equivalent ORM expression starts the JOIN from
# the (huge) marker table; the cold-cache plan misses the
# ``refs_ref_law_slugs_idx`` index and runs 4s on popular sections
# (§ 242 BGB). STRAIGHT_JOIN pins the JOIN order to
# ``reference → markers_references → marker`` so the slug index
# drives the read — consistently ~200ms regardless of plan-cache
# state. On SQLite (tests) we drop the hint; the planner picks the
# index-driven plan unaided on small fixtures.


def _hint() -> str:
    return "STRAIGHT_JOIN" if connection.vendor == "mysql" else ""


def _fetch_ids(sql_template: str, params: tuple) -> list[int]:
    sql = sql_template.format(hint=_hint())
    with connection.cursor() as cur:
        cur.execute(sql, params)
        return [row[0] for row in cur.fetchall() if row[0] is not None]


_CASE_IDS_FROM_CASE_SQL = """
    SELECT {hint} DISTINCT m.referenced_by_id
    FROM references_reference r
    JOIN references_casereferencemarker_references mr ON mr.reference_id = r.id
    JOIN references_casereferencemarker m ON m.id = mr.casereferencemarker_id
    WHERE r.case_id = %s
"""

_CASE_IDS_FROM_SLUG_SQL = """
    SELECT {hint} DISTINCT m.referenced_by_id
    FROM references_reference r
    JOIN references_casereferencemarker_references mr ON mr.reference_id = r.id
    JOIN references_casereferencemarker m ON m.id = mr.casereferencemarker_id
    WHERE r.law_book_slug = %s AND r.law_section_slug = %s
"""

_LAW_IDS_FROM_CASE_SQL = """
    SELECT {hint} DISTINCT m.referenced_by_id
    FROM references_reference r
    JOIN references_lawreferencemarker_references mr ON mr.reference_id = r.id
    JOIN references_lawreferencemarker m ON m.id = mr.lawreferencemarker_id
    WHERE r.case_id = %s
"""

_LAW_IDS_FROM_SLUG_SQL = """
    SELECT {hint} DISTINCT m.referenced_by_id
    FROM references_reference r
    JOIN references_lawreferencemarker_references mr ON mr.reference_id = r.id
    JOIN references_lawreferencemarker m ON m.id = mr.lawreferencemarker_id
    WHERE r.law_book_slug = %s AND r.law_section_slug = %s
"""


def citing_case_ids_for_case(case: Case) -> list[int]:
    """``Case`` ids of cases whose body cites ``case``.

    Lower-level than :func:`citing_cases_for_case` — exposed for
    callers that already have their own case queryset (e.g. preserving
    request-scoped review-status filtering) and just want to constrain
    it via ``id__in=…``.
    """
    return _fetch_ids(_CASE_IDS_FROM_CASE_SQL, (case.id,))


def citing_case_ids_for_slug_pair(book_slug: str, section_slug: str) -> list[int]:
    """``Case`` ids citing the given ``(book_slug, section_slug)`` law section.

    See :func:`citing_case_ids_for_case` for when to prefer this over
    :func:`citing_cases_for_law`.
    """
    return _fetch_ids(_CASE_IDS_FROM_SLUG_SQL, (book_slug, section_slug))


def citing_law_ids_for_case(case: Case) -> list[int]:
    """``Law`` ids of laws whose body cites ``case`` (rare in practice)."""
    return _fetch_ids(_LAW_IDS_FROM_CASE_SQL, (case.id,))


def citing_law_ids_for_slug_pair(book_slug: str, section_slug: str) -> list[int]:
    """``Law`` ids citing the given law section (rare in practice)."""
    return _fetch_ids(_LAW_IDS_FROM_SLUG_SQL, (book_slug, section_slug))


def citing_cases_for_case(case: Case) -> QuerySet[Case]:
    """``Case`` queryset of cases whose body cites ``case``."""
    case_ids = citing_case_ids_for_case(case)
    if not case_ids:
        return Case.objects.none()
    return (
        exclude_future_dated_cases(
            Case.objects.filter(
                id__in=case_ids,
                review_status="accepted",
            )
        )
        .select_related("court")
        .defer(*Case.defer_fields_list_view)
        .order_by("-date")
    )


def citing_cases_for_law(
    law_or_ids: Law | int | Iterable[int] | tuple[str, str],
) -> QuerySet[Case]:
    """``Case`` queryset of cases whose body cites the given law section.

    Accepts:
      - a single ``Law`` instance,
      - a single law id,
      - an iterable of law ids (legacy cross-revision lookup),
      - a ``(book_slug, section_slug)`` tuple — preferred form.

    All forms collapse to a slug-based filter on
    ``Reference.law_book_slug`` + ``Reference.law_section_slug``, which
    survives book-revision turnover and avoids the JOIN through
    ``Law``→``LawBook`` that the legacy id-based query needed.
    """
    pair = (
        law_or_ids if isinstance(law_or_ids, tuple) else _law_to_slug_pair(law_or_ids)
    )
    if not pair:
        return Case.objects.none()
    book_slug, section_slug = pair
    case_ids = citing_case_ids_for_slug_pair(book_slug, section_slug)
    if not case_ids:
        return Case.objects.none()
    return (
        exclude_future_dated_cases(
            Case.objects.filter(
                id__in=case_ids,
                review_status="accepted",
            )
        )
        .select_related("court")
        .defer(*Case.defer_fields_list_view)
        .order_by("-date")
    )


def citing_laws_for_case(case: Case) -> QuerySet[Law]:
    """``Law`` queryset of laws whose body cites ``case``.

    Symmetric to :func:`citing_cases_for_case`. Rare in practice — laws
    overwhelmingly cite other laws, not cases — but exposed for
    symmetry and to support analytical queries against the flat
    ``/api/references/`` resource.
    """
    law_ids = citing_law_ids_for_case(case)
    if not law_ids:
        return Law.objects.none()
    return (
        Law.objects.filter(
            id__in=law_ids,
            review_status="accepted",
            book__latest=True,
        )
        .select_related("book")
        .defer(*Law.defer_fields_list_view)
        .order_by("book__order", "order")
    )


def citing_laws_for_law(
    law_or_ids: Law | int | Iterable[int] | tuple[str, str],
) -> QuerySet[Law]:
    """``Law`` queryset of laws whose body cites the given law section.

    Accepts the same input shapes as :func:`citing_cases_for_law` and
    likewise filters on the stable ``(law_book_slug, law_section_slug)``
    pair on ``Reference``.
    """
    pair = (
        law_or_ids if isinstance(law_or_ids, tuple) else _law_to_slug_pair(law_or_ids)
    )
    if not pair:
        return Law.objects.none()
    book_slug, section_slug = pair
    law_ids = citing_law_ids_for_slug_pair(book_slug, section_slug)
    if not law_ids:
        return Law.objects.none()
    return (
        Law.objects.filter(
            id__in=law_ids,
            review_status="accepted",
            book__latest=True,
        )
        .select_related("book")
        .defer(*Law.defer_fields_list_view)
        .order_by("book__order", "order")
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
    "citing_case_ids_for_case",
    "citing_case_ids_for_slug_pair",
    "citing_cases_for_case",
    "citing_cases_for_law",
    "citing_law_ids_for_case",
    "citing_law_ids_for_slug_pair",
    "citing_laws_for_case",
    "citing_laws_for_law",
    "law_forward_references",
    "resolve_law_section",
    "serialize_case_summary",
    "serialize_law_summary",
]
