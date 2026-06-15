"""Citation parsing + validation.

Determines whether a free-form German citation string (Aktenzeichen,
ECLI, or paragraph reference) corresponds to a row in the local DB.
Mirrors the shape of the legacy ``ReferenceTools.validate_citation``
MCP tool — moved here so REST endpoints can reuse the same logic.

Law-reference parsing is delegated to the ``refex`` package
(legal-reference-extraction), which is the same library used by the
production reference-extraction pipeline. This means
``validate_citation`` accepts every citation shape that the extractor
itself recognises (``§ 823 BGB``, ``§ 823 Abs. 1 Satz 2 BGB``,
``Artikel 1 GG``, ``Art. 14 GG``, ``Art. 15 DSGVO``, …) without
re-implementing — and drifting from — that grammar here.
"""

from __future__ import annotations

import re

from oldp.apps.cases.models import Case
from oldp.apps.laws.models import Law, LawBook

# ECLI has a fixed shape (`ECLI:DE:BGH:2023:…`); refex doesn't parse
# them yet, so a tiny regex is still the cleanest detector. Everything
# else (paragraph/article references, Aktenzeichen) goes through refex.
ECLI_PATTERN = re.compile(r"^ECLI:\w{2}:\w+:\d{4}:[\w.]+$", re.IGNORECASE)

# Lightweight detector for the law_reference vs file_number split in
# parse_citation_type. We don't extract from this — we just need to
# decide which validator to run. refex performs the actual parsing.
_LAW_REFERENCE_HINT = re.compile(r"(?:§|Artikel|Art\.?)\s", re.IGNORECASE)


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
    if _LAW_REFERENCE_HINT.match(citation):
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


def _extract_law_citation(citation: str):
    """Parse a free-form law reference with refex.

    Returns the first ``LawCitation`` (refex result) or ``None`` if
    nothing parses. We import inside the function so a refex import
    failure doesn't break process startup — validation is opt-in per
    request, not a module-load dependency.

    The extractor's recognised-book set is the union of refex's
    bundled list (~1950 codes shipped with the library) and the codes
    actually present in the local DB. The DB additions let test books
    and any OLDP-specific codes resolve without monkeypatching refex;
    the bundle keeps coverage for codes that haven't been ingested
    locally yet.
    """
    from refex.document import make_document
    from refex.engines.regex import RegexLawExtractor
    from refex.orchestrator import CitationExtractor

    engine = RegexLawExtractor()
    db_codes = LawBook.objects.values_list("code", flat=True).distinct()
    engine.law_book_codes = list(set(engine.law_book_codes) | set(db_codes))
    extractor = CitationExtractor(engines=[engine])
    result = extractor.extract(make_document(citation, fmt="text"))
    return next(iter(result.citations), None)


def _validate_law_reference(citation: str) -> dict:
    parsed = _extract_law_citation(citation)
    if parsed is None:
        return {
            "found": False,
            "type": "unknown",
            "message": f"Could not parse law reference: '{citation}'.",
        }

    # refex stores the law book code in lower-case (e.g. ``bgb``) and
    # the section number as a bare string ("823", "16a"). Resolve via
    # case-insensitive matching to be tolerant of either form.
    book_code = parsed.book or ""
    section = parsed.number or ""

    book = LawBook.objects.filter(
        code__iexact=book_code,
        latest=True,
        review_status="accepted",
    ).first()
    if not book:
        from oldp.apps.laws.suggestions import suggest_book_codes

        result = {
            "found": False,
            "type": "law",
            "citation_type": "law_reference",
            "message": f"Law book '{book_code}' not found.",
        }
        suggestions = suggest_book_codes(book_code)
        if suggestions:
            result["suggestions"] = suggestions
        return result

    # Try refex's bare-number form first (the most common storage), then
    # the common prefixed variants ("§ N", "Artikel N", …). Stop at the
    # first variant that yields hits and only accept exact matches; an
    # icontains fallback would surface spurious siblings (e.g. "§ 1823"
    # for "§ 823", "§ 132" for "§ 32").
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
            f"Section '{section}' not found in {book.code}. "
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
            ``"ECLI:DE:BGH:2023:..."``, ``"§ 823 BGB"``,
            ``"Artikel 1 GG"``).
        citation_type: ``"auto"`` (default), ``"file_number"``,
            ``"ecli"``, or ``"law_reference"``.

    Returns:
        A dict with ``found``, ``type``, and either ``matches`` (list of
        record dicts) or ``message`` (human-readable not-found text).
        When the caller passes an explicit ``citation_type`` that
        conflicts with what auto-detection would have chosen, the
        response also includes ``input_type_mismatch`` describing the
        conflict so confused inputs aren't silently mis-routed.
    """
    citation = (citation or "").strip()
    if not citation:
        return {"error": "Citation cannot be empty."}

    detected_type = parse_citation_type(citation)
    mismatch_warning: dict | None = None
    if citation_type == "auto":
        citation_type = detected_type
    elif citation_type != detected_type:
        # Honour the caller's explicit override, but include a warning
        # so confused inputs don't silently return cryptic "not found"
        # messages. Common case: passing citation_type="ecli" for an
        # Aktenzeichen.
        mismatch_warning = {
            "requested_type": citation_type,
            "detected_type": detected_type,
            "message": (
                f"Input looks like '{detected_type}' but citation_type="
                f"'{citation_type}' was forced; results may be empty."
            ),
        }

    if citation_type == "ecli":
        result = _validate_ecli(citation)
    elif citation_type == "law_reference":
        result = _validate_law_reference(citation)
    else:
        result = _validate_file_number(citation)

    if mismatch_warning is not None:
        result["input_type_mismatch"] = mismatch_warning
    return result


__all__ = [
    "ECLI_PATTERN",
    "parse_citation_type",
    "section_variants",
    "validate_citation",
]
