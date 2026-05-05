"""MCP tools for citation validation and cross-reference navigation.

These tools expose OLDP's unique cross-reference capabilities, enabling
AI agents to navigate the citation graph between cases and laws.
"""

import logging
import re

from mcp_server import MCPToolset

from oldp.apps.cases.models import Case
from oldp.apps.laws.models import Law, LawBook
from oldp.apps.mcp.monitoring import log_tool_call
from oldp.apps.references.models import CaseReferenceMarker

logger = logging.getLogger("oldp.mcp.tools")

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
                    laws = list(
                        Law.objects.filter(
                            book=book,
                            section__iexact=section,
                            review_status="accepted",
                        )[:5]
                    )
                    if not laws:
                        # Try partial match
                        laws = list(
                            Law.objects.filter(
                                book=book,
                                section__icontains=section,
                                review_status="accepted",
                            )[:5]
                        )
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

        # Default: file number (Aktenzeichen)
        cases = list(
            Case.objects.filter(
                file_number__iexact=citation, review_status="accepted"
            ).select_related("court")[:5]
        )
        if not cases:
            # Try partial match
            cases = list(
                Case.objects.filter(
                    file_number__icontains=citation, review_status="accepted"
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

        return {
            "case_id": case_id,
            "case_file_number": case.file_number,
            "total_law_references": len(law_refs),
            "total_case_references": len(case_refs),
            "law_references": law_refs,
            "case_references": case_refs,
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
        citing_qs = Case.objects.filter(
            casereferencemarker__references__case_id=case_id,
            review_status="accepted",
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

        law = None
        if law_id:
            law = Law.objects.filter(id=law_id, review_status="accepted").first()
        elif book_code and section:
            book = LawBook.objects.filter(
                code__iexact=book_code,
                latest=True,
                review_status="accepted",
            ).first()
            if not book:
                return {"error": f"Law book '{book_code}' not found."}
            law = Law.objects.filter(
                book=book,
                section__iexact=section,
                review_status="accepted",
            ).first()
        else:
            return {
                "error": "Provide either law_id, or both book_code and section.",
            }

        if not law:
            return {
                "error": f"Law section not found for book='{book_code}', section='{section}'.",
            }

        # Single filtered queryset; evaluate once for the ordered slice and
        # reuse the sliced list to avoid a second .distinct().count() over
        # the 3-JOIN graph when we already have the full result set.
        citing_qs = Case.objects.filter(
            casereferencemarker__referencefromcase__reference__law=law,
            review_status="accepted",
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
            "law_id": law.id,
            "book_code": law.book.code if law.book_id else "",
            "section": law.section,
            "total_citing_cases": total,
            "results": results,
        }
