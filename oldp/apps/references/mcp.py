"""MCP tools for citation validation and cross-reference navigation.

These tools expose OLDP's cross-reference capabilities, enabling AI agents
to navigate the citation graph between cases and laws. Implementation
delegates to :mod:`oldp.apps.references.services` so the REST endpoints
share the same query / serialization logic.
"""

import logging

from mcp_server import MCPToolset

from oldp.apps.cases.models import Case
from oldp.apps.laws.models import Law
from oldp.apps.mcp.monitoring import log_tool_call
from oldp.apps.mcp.utils import clamp_limit, with_limit_meta
from oldp.apps.references.services import (
    case_forward_references,
    citing_cases_for_case,
    citing_cases_for_law,
    resolve_law_section,
    serialize_case_summary,
    validate_citation,
)

logger = logging.getLogger("oldp.mcp.tools")


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
        return validate_citation(citation, citation_type)

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
        return case_forward_references(case)

    @log_tool_call
    def get_citing_cases(
        self,
        case_id: int,
        limit: int = 20,
    ) -> dict:
        """Get reverse references TO a case (cases that cite this case).

        Find all cases that reference the given case in their text.
        Useful for understanding the impact and precedent value of a
        decision.

        Args:
            case_id: The database ID of the cited case.
            limit: Maximum results (default 20, max 50). Values above 50 are
                clamped; the response then includes ``limit_clamped: true``
                and the original ``requested_limit``.
        """
        requested_limit = limit
        limit, limit_was_clamped = clamp_limit(limit, maximum=50)

        case = Case.objects.filter(id=case_id, review_status="accepted").first()
        if not case:
            return {"error": f"Case with ID {case_id} not found."}

        qs = citing_cases_for_case(case)
        # Materialise the limited slice once; reuse for total to avoid
        # running the same DISTINCT JOIN twice when result count <= limit.
        sliced = list(qs[:limit])
        if len(sliced) < limit:
            total = len(sliced)
        else:
            total = qs.count()

        return with_limit_meta(
            {
                "cited_case_id": case_id,
                "cited_case_file_number": case.file_number,
                "total_citing_cases": total,
                "results": [serialize_case_summary(c) for c in sliced],
            },
            requested=requested_limit,
            applied=limit,
            was_clamped=limit_was_clamped,
            maximum=50,
        )

    @log_tool_call
    def get_cases_for_law(
        self,
        book_code: str = "",
        section: str = "",
        law_id: int = 0,
        limit: int = 20,
    ) -> dict:
        """Find all cases that cite a specific law section.

        Returns cases that reference the given statute section in their
        text. Useful for understanding how courts interpret a specific
        provision.

        Args:
            book_code: Law book code (e.g. "BGB", "StGB").
            section: Section identifier (e.g. "823").
            law_id: Direct law database ID (alternative to book_code+section).
            limit: Maximum results (default 20, max 50). Values above 50 are
                clamped; the response then includes ``limit_clamped: true``
                and the original ``requested_limit``.
        """
        requested_limit = limit
        limit, limit_was_clamped = clamp_limit(limit, maximum=50)

        primary: Law | None = None
        law_ids: list[int] = []

        if law_id:
            primary = (
                Law.objects.filter(id=law_id, review_status="accepted")
                .select_related("book")
                .first()
            )
            if primary:
                law_ids = [primary.id]
        elif book_code and section:
            primary, law_ids = resolve_law_section(book_code, section)
            if primary is None and not law_ids:
                # Distinguish "book unknown" from "book exists but section
                # missing" so callers get a precise hint.
                from oldp.apps.laws.models import LawBook

                if not LawBook.objects.filter(
                    code__iexact=book_code, review_status="accepted"
                ).exists():
                    return {"error": f"Law book '{book_code}' not found."}
        else:
            return {
                "error": "Provide either law_id, or both book_code and section.",
            }

        if not primary or not law_ids:
            return {
                "error": (
                    f"Law section not found for book='{book_code}', "
                    f"section='{section}'."
                ),
            }

        qs = citing_cases_for_law(law_ids)
        sliced = list(qs[:limit])
        if len(sliced) < limit:
            total = len(sliced)
        else:
            total = qs.count()

        return with_limit_meta(
            {
                "law_id": primary.id,
                "book_code": primary.book.code if primary.book_id else "",
                "section": primary.section,
                "total_citing_cases": total,
                "results": [serialize_case_summary(c) for c in sliced],
            },
            requested=requested_limit,
            applied=limit,
            was_clamped=limit_was_clamped,
            maximum=50,
        )
