"""MCP tools for court discovery and retrieval."""

from django.db.models import Count, Q
from mcp_server import MCPToolset

from oldp.apps.courts.models import Court


class CourtTools(MCPToolset):
    """Tools for browsing and retrieving court information."""

    def list_courts(
        self,
        court_type: str = "",
        state: str = "",
        jurisdiction: str = "",
        level_of_appeal: str = "",
        search: str = "",
        limit: int = 50,
    ) -> list[dict]:
        """Browse and filter German courts.

        Returns a list of courts matching the given filters. Use this to
        discover which courts are available before searching for cases.

        Args:
            court_type: Filter by court type code (e.g. "AG", "LG", "OLG",
                "BGH", "VG", "OVG", "BVerwG", "ArbG", "LAG", "BAG").
            state: Filter by state name or slug (e.g. "Berlin", "bayern").
            jurisdiction: Filter by jurisdiction (e.g. "ordinary",
                "administrative", "labor", "social", "fiscal").
            level_of_appeal: Filter by level (e.g. "local", "regional",
                "high", "federal").
            search: Search court names and aliases.
            limit: Maximum results to return (default 50, max 100).
        """
        limit = min(max(1, limit), 100)
        qs = Court.objects.filter(review_status="accepted").select_related(
            "state", "city"
        )

        if court_type:
            qs = qs.filter(court_type__iexact=court_type)
        if state:
            qs = qs.filter(
                Q(state__name__icontains=state) | Q(state__slug__iexact=state)
            )
        if jurisdiction:
            qs = qs.filter(jurisdiction__icontains=jurisdiction)
        if level_of_appeal:
            qs = qs.filter(level_of_appeal__icontains=level_of_appeal)
        if search:
            qs = qs.filter(Q(name__icontains=search) | Q(aliases__icontains=search))

        qs = qs.annotate(case_count=Count("case")).order_by("-case_count")

        results = []
        for court in qs[:limit]:
            results.append(
                {
                    "id": court.id,
                    "name": court.name,
                    "slug": court.slug,
                    "code": court.code,
                    "court_type": court.court_type,
                    "state": court.state.name if court.state else None,
                    "city": court.city.name if court.city else None,
                    "jurisdiction": court.jurisdiction,
                    "level_of_appeal": court.level_of_appeal,
                    "case_count": court.case_count,
                }
            )

        if not results:
            return {
                "results": [],
                "message": "No courts found matching your filters. Try broadening your search.",
            }

        return {"total": qs.count(), "results": results}

    def get_court(
        self,
        court_id: int = 0,
        slug: str = "",
        code: str = "",
    ) -> dict:
        """Get detailed information about a specific court.

        Look up a court by ID, slug, or code. Returns full details including
        address, contact information, and case count.

        Args:
            court_id: Court database ID.
            slug: Court slug (e.g. "ag-berlin-charlottenburg").
            code: Court ECLI code (e.g. "AGBCHAR").
        """
        qs = Court.objects.filter(review_status="accepted").select_related(
            "state", "city"
        )

        court = None
        if court_id:
            court = qs.filter(id=court_id).first()
        elif slug:
            court = qs.filter(slug=slug).first()
        elif code:
            court = qs.filter(code=code).first()

        if not court:
            return {
                "error": "Court not found. Provide a valid court_id, slug, or code.",
            }

        case_count = court.case_set.filter(review_status="accepted").count()

        return {
            "id": court.id,
            "name": court.name,
            "slug": court.slug,
            "code": court.code,
            "court_type": court.court_type,
            "state": court.state.name if court.state else None,
            "city": court.city.name if court.city else None,
            "jurisdiction": court.jurisdiction,
            "level_of_appeal": court.level_of_appeal,
            "description": court.description or "",
            "homepage": court.homepage or "",
            "street_address": court.street_address or "",
            "postal_code": court.postal_code or "",
            "address_locality": court.address_locality or "",
            "telephone": court.telephone or "",
            "fax_number": court.fax_number or "",
            "email": court.email or "",
            "case_count": case_count,
        }
