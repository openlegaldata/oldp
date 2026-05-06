"""MCP tools for citation validation and cross-reference navigation.

These tools expose OLDP's unique cross-reference capabilities, enabling
AI agents to navigate the citation graph between cases and laws.
"""

import datetime
import logging
import re

from mcp_server import MCPToolset

from oldp.apps.cases.mcp import exclude_future_dated_cases
from oldp.apps.cases.models import Case
from oldp.apps.laws.models import Law, LawBook
from oldp.apps.mcp.monitoring import log_tool_call
from oldp.apps.references.models import CaseReferenceMarker

logger = logging.getLogger("oldp.mcp.tools")


def _section_variants(section):
    """Return likely DB representations of a user-provided section identifier.

    Users typically pass bare numbers ("823", "16a"), but the database stores
    fully-qualified identifiers — "§ 823" for most codes and "Artikel 1" for
    the Grundgesetz. Try the input as-is first, then prepend the common
    German legal prefixes.
    """
    s = (section or "").strip()
    if not s:
        return []
    # If the caller already included a prefix, trust it and search only for
    # that exact form rather than expanding into ambiguous variants.
    if s.startswith("§") or s.lower().startswith(("art", "artikel")):
        return [s]
    return [s, f"§ {s}", f"Artikel {s}", f"Art. {s}"]


# Regex patterns for German citation formats
ECLI_PATTERN = re.compile(r"^ECLI:\w{2}:\w+:\d{4}:[\w.]+$", re.IGNORECASE)
PARAGRAPH_PATTERN = re.compile(
    r"(?:§|Art\.?)\s*([\d\w]+(?:\s*[a-z])?)\s+(\w+)", re.IGNORECASE
)


def _parse_citation_type(citation):
    """Detect the type of a German legal citation."""
    citation = citation.strip()
    if ECLI_PATTERN.match(citation):
        return "ecli"
    if PARAGRAPH_PATTERN.match(citation):
        return "law_reference"
    # Default: assume file number (Aktenzeichen)
    return "file_number"


class ReferenceTools(MCPToolset):
    """Tools for citation validation and cross-reference navigation.

    References are automatically extracted and may be incomplete or contain
    errors. Verify critical citations against the full case text.
    """

    @log_tool_call
    def validate_citation(
        self,
        citation: str,
        citation_type: str = "auto",
    ) -> dict:
        """Check if a legal citation exists in the OLDP database.

        Validates Aktenzeichen (file numbers), ECLI identifiers, or
        paragraph references (e.g. "§ 823 BGB"). Use this to verify
        citations before presenting them to users.

        Args:
            citation: The citation to validate (e.g. "VI ZR 123/22",
                "ECLI:DE:BGH:2023:...", "§ 823 BGB").
            citation_type: Type hint: "auto" (default), "file_number",
                "ecli", or "law_reference".
        """
        citation = citation.strip()
        if not citation:
            return {"error": "Citation cannot be empty."}

        if citation_type == "auto":
            citation_type = _parse_citation_type(citation)

        if citation_type == "ecli":
            cases = list(
                Case.objects.filter(
                    ecli__iexact=citation, review_status="accepted"
                ).select_related("court")[:5]
            )
            if cases:
                return {
                    "found": True,
                    "type": "case",
                    "matches": [
                        {
                            "id": c.id,
                            "slug": c.slug,
                            "file_number": c.file_number,
                            "date": str(c.date) if c.date else None,
                            "court": c.court.name if c.court else None,
                            "ecli": c.ecli,
                        }
                        for c in cases
                    ],
                }
            return {
                "found": False,
                "type": "case",
                "citation_type": "ecli",
                "message": f"ECLI '{citation}' not found in database.",
            }

        if citation_type == "law_reference":
            match = PARAGRAPH_PATTERN.match(citation)
            if match:
                section = match.group(1).strip()
                book_code = match.group(2).strip()
                book = LawBook.objects.filter(
                    code__iexact=book_code,
                    latest=True,
                    review_status="accepted",
                ).first()
                if book:
                    # Try the user-provided form, then the common
                    # German prefixed variants ("§ N", "Artikel N", ...).
                    # Stop at the first variant that yields hits and only
                    # accept exact matches; an icontains fallback would
                    # produce spurious siblings (e.g. "§ 1823" for
                    # "§ 823 BGB", "§ 132" for "§ 32 StGB").
                    laws = []
                    for variant in _section_variants(section):
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
                            "matches": [
                                {
                                    "id": law.id,
                                    "book_code": book.code,
                                    "section": law.section,
                                    "title": law.title,
                                    "slug": law.slug,
                                }
                                for law in laws
                            ],
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
                return {
                    "found": False,
                    "type": "law",
                    "citation_type": "law_reference",
                    "message": f"Law book '{book_code}' not found.",
                }

            return {
                "found": False,
                "type": "unknown",
                "message": f"Could not parse law reference: '{citation}'.",
            }

        # Default: file number (Aktenzeichen). Use exact-match only —
        # the previous icontains fallback ran a `LIKE '%…%'` scan over
        # the whole Case table, which has no trigram index in production
        # and timed out for invalid inputs. Validation is supposed to be
        # strict; for fuzzy file-number lookup callers should use
        # filter_cases instead.
        cases = list(
            Case.objects.filter(
                file_number__iexact=citation, review_status="accepted"
            ).select_related("court")[:5]
        )
        if cases:
            return {
                "found": True,
                "type": "case",
                "matches": [
                    {
                        "id": c.id,
                        "slug": c.slug,
                        "file_number": c.file_number,
                        "date": str(c.date) if c.date else None,
                        "court": c.court.name if c.court else None,
                        "ecli": c.ecli,
                    }
                    for c in cases
                ],
            }

        return {
            "found": False,
            "type": "case",
            "citation_type": "file_number",
            "message": f"File number '{citation}' not found in database.",
        }

    @log_tool_call
    def get_case_references(self, case_id: int) -> dict:
        """Get forward references FROM a case (what this case cites).

        Returns all laws and cases that the given case references in its
        text. Useful for understanding the legal basis of a decision.

        Args:
            case_id: The database ID of the case.
        """
        case = Case.objects.filter(id=case_id, review_status="accepted").first()
        if not case:
            return {"error": f"Case with ID {case_id} not found."}

        # Use prefetch_related so we resolve all references + their targets
        # (Law and Case) in a constant number of queries regardless of the
        # number of markers. This avoids N+1 on ref.law / ref.case access.
        markers = CaseReferenceMarker.objects.filter(
            referenced_by=case
        ).prefetch_related(
            "references",
            "references__law",
            "references__law__book",
            "references__case",
        )

        law_refs = []
        case_refs = []
        seen_law_ids: set[int] = set()
        seen_case_ids: set[int] = set()

        for marker in markers:
            for ref in marker.references.all():
                if ref.law_id and ref.law_id not in seen_law_ids:
                    seen_law_ids.add(ref.law_id)
                    law = ref.law
                    if law is not None:
                        law_refs.append(
                            {
                                "id": law.id,
                                "book_code": law.book.code if law.book_id else "",
                                "section": law.section,
                                "title": law.title,
                                "marker_text": marker.text,
                            }
                        )
                if ref.case_id and ref.case_id not in seen_case_ids:
                    seen_case_ids.add(ref.case_id)
                    target_case = ref.case
                    if target_case is not None:
                        case_refs.append(
                            {
                                "id": target_case.id,
                                "slug": target_case.slug,
                                "file_number": target_case.file_number,
                                "date": (
                                    str(target_case.date) if target_case.date else None
                                ),
                                "marker_text": marker.text,
                            }
                        )

        # `references_extracted_at` is populated by the extract_refs
        # processing step (oldp/apps/cases/processing/processing_steps/
        # extract_refs.py). A null value means extraction has never run
        # for this case, so an empty references list is genuinely "we
        # don't know" rather than "the extractor found nothing" — the
        # signal callers need to decide whether to trust the list or
        # fall back to reading the full text.
        return {
            "case_id": case_id,
            "case_file_number": case.file_number,
            "total_law_references": len(law_refs),
            "total_case_references": len(case_refs),
            "law_references": law_refs,
            "case_references": case_refs,
            "references_extracted_at": (
                case.references_extracted_at.isoformat()
                if case.references_extracted_at
                else None
            ),
            "note": (
                "References are automatically extracted and may be "
                "incomplete. Verify critical citations against the full text."
            ),
        }

    @log_tool_call
    def get_citing_cases(
        self,
        case_id: int,
        limit: int = 20,
    ) -> dict:
        """Get reverse references TO a case (cases that cite this case).

        Find all cases that reference the given case in their text.
        Useful for understanding the impact and precedent value of a decision.

        Args:
            case_id: The database ID of the cited case.
            limit: Maximum results (default 20, max 50).
        """
        limit = min(max(1, limit), 50)

        case = Case.objects.filter(id=case_id, review_status="accepted").first()
        if not case:
            return {"error": f"Case with ID {case_id} not found."}

        # Single JOIN-based query replaces the previous 4-query chain
        # (Reference -> ReferenceFromCase -> markers -> Case twice).
        citing_qs = exclude_future_dated_cases(
            Case.objects.filter(
                casereferencemarker__references__case_id=case_id,
                review_status="accepted",
            )
        ).distinct()

        # Materialise the limited slice once; reuse for total to avoid running
        # the same DISTINCT JOIN twice when result count <= limit.
        ordered = citing_qs.select_related("court").order_by("-date")
        sliced = list(ordered[:limit])

        if len(sliced) < limit:
            total = len(sliced)
        else:
            total = citing_qs.count()

        results = [
            {
                "id": c.id,
                "slug": c.slug,
                "file_number": c.file_number,
                "date": str(c.date) if c.date else None,
                "court": c.court.name if c.court else None,
                "type": c.type,
            }
            for c in sliced
        ]

        return {
            "cited_case_id": case_id,
            "cited_case_file_number": case.file_number,
            "total_citing_cases": total,
            "results": results,
        }

    @log_tool_call
    def get_cases_for_law(
        self,
        book_code: str = "",
        section: str = "",
        law_id: int = 0,
        limit: int = 20,
    ) -> dict:
        """Find all cases that cite a specific law section.

        Returns cases that reference the given statute section in their text.
        Useful for understanding how courts interpret a specific provision.

        Args:
            book_code: Law book code (e.g. "BGB", "StGB").
            section: Section identifier (e.g. "823").
            law_id: Direct law database ID (alternative to book_code+section).
            limit: Maximum results (default 20, max 50).
        """
        limit = min(max(1, limit), 50)

        primary = None
        law_ids = []

        if law_id:
            primary = (
                Law.objects.filter(id=law_id, review_status="accepted")
                .select_related("book")
                .first()
            )
            if primary:
                law_ids = [primary.id]
        elif book_code and section:
            # Verify the book exists at all (any revision) so we can give
            # a precise error when the code is unknown.
            if not LawBook.objects.filter(
                code__iexact=book_code, review_status="accepted"
            ).exists():
                return {"error": f"Law book '{book_code}' not found."}

            # Aggregate matching Law rows across ALL revisions of the book.
            # The citation graph FK (Reference.law_id) pins references to
            # the specific Law row that existed when extraction ran, which
            # may belong to an older book revision (latest=False). If we
            # only checked the latest revision we'd miss every citation
            # extracted before the most recent revision was added — e.g.
            # for BGB § 823 the live citation graph points at an older
            # revision id while the latest revision has its own row.
            laws_qs = Law.objects.filter(
                book__code__iexact=book_code,
                review_status="accepted",
            ).select_related("book")

            matched = []
            for variant in _section_variants(section):
                matched = list(laws_qs.filter(section__iexact=variant))
                if matched:
                    break

            if matched:
                # For the response payload report a canonical "primary" row:
                # prefer the Law whose book is marked latest=True (the row
                # `get_law_section` would surface), falling back to the most
                # recent revision_date.
                primary = next(
                    (law for law in matched if law.book.latest),
                    max(
                        matched,
                        key=lambda law: law.book.revision_date or datetime.date.min,
                    ),
                )
                law_ids = [law.id for law in matched]
        else:
            return {
                "error": "Provide either law_id, or both book_code and section.",
            }

        if not primary or not law_ids:
            return {
                "error": f"Law section not found for book='{book_code}', section='{section}'.",
            }

        # Single filtered queryset; evaluate once for the ordered slice and
        # reuse the sliced list to avoid a second .distinct().count() over
        # the 3-JOIN graph when we already have the full result set.
        citing_qs = exclude_future_dated_cases(
            Case.objects.filter(
                casereferencemarker__referencefromcase__reference__law_id__in=law_ids,
                review_status="accepted",
            )
        ).distinct()

        ordered = citing_qs.select_related("court").order_by("-date")
        sliced = list(ordered[:limit])

        if len(sliced) < limit:
            total = len(sliced)
        else:
            total = citing_qs.count()

        results = [
            {
                "id": c.id,
                "slug": c.slug,
                "file_number": c.file_number,
                "date": str(c.date) if c.date else None,
                "court": c.court.name if c.court else None,
                "type": c.type,
            }
            for c in sliced
        ]

        return {
            "law_id": primary.id,
            "book_code": primary.book.code if primary.book_id else "",
            "section": primary.section,
            "total_citing_cases": total,
            "results": results,
        }
