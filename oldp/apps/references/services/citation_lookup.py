"""Citation parsing + validation.

Determines whether a free-form German citation string (Aktenzeichen,
ECLI, or paragraph reference) corresponds to a row in the local DB.
Mirrors the shape of the legacy ``ReferenceTools.validate_citation``
MCP tool — moved here so REST endpoints can reuse the same logic.
"""

from __future__ import annotations

import re

from oldp.apps.cases.models import Case
from oldp.apps.laws.models import Law, LawBook

# Regex patterns for German citation formats.
ECLI_PATTERN = re.compile(r"^ECLI:\w{2}:\w+:\d{4}:[\w.]+$", re.IGNORECASE)
PARAGRAPH_PATTERN = re.compile(
    r"(?:§|Art\.?)\s*([\d\w]+(?:\s*[a-z])?)\s+(\w+)", re.IGNORECASE
)


def section_variants(section: str) -> list[str]:
    """Return likely DB representations of a user-provided section identifier.

    Users typically pass bare numbers ("823", "16a"), but the database
    stores fully-qualified identifiers — "§ 823" for most codes and
    "Artikel 1" for the Grundgesetz. Try the input as-is first, then
    prepend the common German legal prefixes. If the caller already
    included a prefix, trust it and search only that exact form rather
    than expanding into ambiguous variants.
    """
    s = (section or "").strip()
    if not s:
        return []
    if s.startswith("§") or s.lower().startswith(("art", "artikel")):
        return [s]
    return [s, f"§ {s}", f"Artikel {s}", f"Art. {s}"]


def parse_citation_type(citation: str) -> str:
    """Detect the type of a German legal citation.

    Returns ``"ecli"``, ``"law_reference"``, or ``"file_number"`` (the
    default when no other pattern matches).
    """
    citation = citation.strip()
    if ECLI_PATTERN.match(citation):
        return "ecli"
    if PARAGRAPH_PATTERN.match(citation):
        return "law_reference"
    return "file_number"


def _serialize_case_match(case: Case) -> dict:
    return {
        "id": case.id,
        "slug": case.slug,
        "file_number": case.file_number,
        "date": str(case.date) if case.date else None,
        "court": case.court.name if case.court else None,
        "ecli": case.ecli,
    }


def _serialize_law_match(law: Law, book_code: str) -> dict:
    return {
        "id": law.id,
        "book_code": book_code,
        "section": law.section,
        "title": law.title,
        "slug": law.slug,
    }


def _validate_ecli(citation: str) -> dict:
    cases = list(
        Case.objects.filter(
            ecli__iexact=citation, review_status="accepted"
        ).select_related("court")[:5]
    )
    if cases:
        return {
            "found": True,
            "type": "case",
            "matches": [_serialize_case_match(c) for c in cases],
        }
    return {
        "found": False,
        "type": "case",
        "citation_type": "ecli",
        "message": f"ECLI '{citation}' not found in database.",
    }


def _validate_law_reference(citation: str) -> dict:
    match = PARAGRAPH_PATTERN.match(citation)
    if not match:
        return {
            "found": False,
            "type": "unknown",
            "message": f"Could not parse law reference: '{citation}'.",
        }

    section = match.group(1).strip()
    book_code = match.group(2).strip()
    book = LawBook.objects.filter(
        code__iexact=book_code,
        latest=True,
        review_status="accepted",
    ).first()
    if not book:
        return {
            "found": False,
            "type": "law",
            "citation_type": "law_reference",
            "message": f"Law book '{book_code}' not found.",
        }

    # Try the user-provided form, then the common German prefixed
    # variants ("§ N", "Artikel N", ...). Stop at the first variant
    # that yields hits and only accept exact matches; an icontains
    # fallback would produce spurious siblings (e.g. "§ 1823" for
    # "§ 823 BGB", "§ 132" for "§ 32 StGB").
    laws: list[Law] = []
    for variant in section_variants(section):
        laws = list(
            Law.objects.filter(
                book=book,
                section__iexact=variant,
                review_status="accepted",
            )[:5]
        )
        if laws:
            break

    if laws:
        return {
            "found": True,
            "type": "law",
            "matches": [_serialize_law_match(law, book.code) for law in laws],
        }
    return {
        "found": False,
        "type": "law",
        "citation_type": "law_reference",
        "message": (
            f"Section '{section}' not found in {book_code}. "
            "Use list_law_books to check available books."
        ),
    }


def _validate_file_number(citation: str) -> dict:
    # Use exact-match only — the previous icontains fallback ran a
    # ``LIKE '%…%'`` scan over the whole Case table, which has no
    # trigram index in production and timed out for invalid inputs.
    # Validation is supposed to be strict; for fuzzy file-number
    # lookup callers should use filter_cases instead.
    cases = list(
        Case.objects.filter(
            file_number__iexact=citation, review_status="accepted"
        ).select_related("court")[:5]
    )
    if cases:
        return {
            "found": True,
            "type": "case",
            "matches": [_serialize_case_match(c) for c in cases],
        }
    return {
        "found": False,
        "type": "case",
        "citation_type": "file_number",
        "message": f"File number '{citation}' not found in database.",
    }


def validate_citation(citation: str, citation_type: str = "auto") -> dict:
    """Validate a German legal citation against the local DB.

    Args:
        citation: The citation string (e.g. ``"VI ZR 123/22"``,
            ``"ECLI:DE:BGH:2023:..."``, ``"§ 823 BGB"``).
        citation_type: ``"auto"`` (default), ``"file_number"``,
            ``"ecli"``, or ``"law_reference"``.

    Returns:
        A dict with ``found``, ``type``, and either ``matches`` (list of
        record dicts) or ``message`` (human-readable not-found text).
        Mirrors the shape of the MCP ``validate_citation`` tool.
    """
    citation = (citation or "").strip()
    if not citation:
        return {"error": "Citation cannot be empty."}

    if citation_type == "auto":
        citation_type = parse_citation_type(citation)

    if citation_type == "ecli":
        return _validate_ecli(citation)
    if citation_type == "law_reference":
        return _validate_law_reference(citation)
    return _validate_file_number(citation)


__all__ = [
    "ECLI_PATTERN",
    "PARAGRAPH_PATTERN",
    "parse_citation_type",
    "section_variants",
    "validate_citation",
]
