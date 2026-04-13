"""MCP tools for case search, filtering, retrieval, and statistics."""

import datetime
import logging

from django.db.models import Count
from django.db.models.functions import TruncMonth, TruncYear
from mcp_server import MCPToolset

from oldp.apps.cases.models import Case

logger = logging.getLogger(__name__)

# Maximum content length returned by default
DEFAULT_TRUNCATE_LENGTH = 30000
FULL_TEXT_MAX_LENGTH = 100000


class CaseTools(MCPToolset):
    """Tools for searching, filtering, and retrieving court cases."""

    def search_cases(
        self,
        query: str,
        court_code: str = "",
        start_date: str = "",
        end_date: str = "",
        decision_type: str = "",
        limit: int = 10,
    ) -> dict:
        """Full-text search for German court cases via Elasticsearch.

        Returns matching cases with highlighted snippets. Does NOT return
        full case text - use get_case to retrieve complete content.

        Args:
            query: Search query text (supports Lucene syntax).
            court_code: Filter by court code (e.g. "BGH", "BVerfG").
            start_date: Filter cases from this date (YYYY-MM-DD).
            end_date: Filter cases up to this date (YYYY-MM-DD).
            decision_type: Filter by decision type (e.g. "Urteil", "Beschluss").
            limit: Maximum results (default 10, max 50).
        """
        limit = min(max(1, limit), 50)

        try:
            from oldp.apps.search.api import SearchQueryBuilder

            builder = SearchQueryBuilder()
            builder.filter_models([Case])
            builder.filter_review_status("accepted")
            builder.apply_highlight()
            builder.apply_date_range(start_date, end_date)
            sqs = builder.build().auto_query(query)

            if court_code:
                sqs = sqs.filter(court=court_code)
            if decision_type:
                sqs = sqs.filter(decision_type=decision_type)

            results = []
            for result in sqs[:limit]:
                snippets = []
                if hasattr(result, "highlighted") and result.highlighted:
                    snippets = result.highlighted[:3]
                elif hasattr(result, "text") and result.text:
                    snippets = [result.text[:200]]

                results.append(
                    {
                        "id": result.pk,
                        "slug": getattr(result, "slug", ""),
                        "date": str(getattr(result, "date", "")),
                        "court": getattr(result, "court", ""),
                        "court_jurisdiction": getattr(result, "court_jurisdiction", ""),
                        "court_level_of_appeal": getattr(
                            result, "court_level_of_appeal", ""
                        ),
                        "decision_type": getattr(result, "decision_type", ""),
                        "snippets": snippets,
                    }
                )

            total = sqs.count()

            if not results:
                return {
                    "results": [],
                    "total": 0,
                    "message": (
                        f"No cases found for query '{query}'. "
                        "Try different search terms or broader filters."
                    ),
                }

            return {"total": total, "results": results}

        except Exception as exc:
            logger.warning("Case search failed: %s", exc)
            return {
                "error": (
                    "Search is temporarily unavailable. Use filter_cases "
                    "for structured queries instead."
                ),
            }

    def filter_cases(
        self,
        court_id: int = 0,
        court_slug: str = "",
        date_after: str = "",
        date_before: str = "",
        file_number: str = "",
        ecli: str = "",
        decision_type: str = "",
        limit: int = 20,
        offset: int = 0,
    ) -> dict:
        """Structured filtering of court cases using the database.

        Unlike search_cases (which uses full-text search), this tool filters
        cases using exact database fields. Returns case metadata without
        full content.

        Args:
            court_id: Filter by court database ID.
            court_slug: Filter by court slug (e.g. "bgh").
            date_after: Cases from this date onward (YYYY-MM-DD).
            date_before: Cases up to this date (YYYY-MM-DD).
            file_number: Exact file number (Aktenzeichen).
            ecli: Exact ECLI identifier.
            decision_type: Decision type (e.g. "Urteil", "Beschluss").
            limit: Maximum results (default 20, max 50).
            offset: Skip first N results for pagination (default 0).
        """
        limit = min(max(1, limit), 50)
        offset = max(0, offset)

        qs = Case.objects.filter(review_status="accepted").select_related("court")

        if court_id:
            qs = qs.filter(court_id=court_id)
        if court_slug:
            qs = qs.filter(court__slug=court_slug)
        if date_after:
            try:
                qs = qs.filter(date__gte=datetime.date.fromisoformat(date_after))
            except ValueError:
                return {
                    "error": f"Invalid date_after format: '{date_after}'. Use YYYY-MM-DD."
                }
        if date_before:
            try:
                qs = qs.filter(date__lte=datetime.date.fromisoformat(date_before))
            except ValueError:
                return {
                    "error": f"Invalid date_before format: '{date_before}'. Use YYYY-MM-DD."
                }
        if file_number:
            qs = qs.filter(file_number=file_number)
        if ecli:
            qs = qs.filter(ecli=ecli)
        if decision_type:
            qs = qs.filter(type__icontains=decision_type)

        qs = qs.order_by("-date")
        total = qs.count()

        results = []
        for case in qs[offset : offset + limit]:
            results.append(
                {
                    "id": case.id,
                    "slug": case.slug,
                    "file_number": case.file_number,
                    "date": str(case.date) if case.date else None,
                    "court_name": case.court.name if case.court else None,
                    "court_slug": case.court.slug if case.court else None,
                    "type": case.type,
                    "ecli": case.ecli,
                }
            )

        if not results:
            return {
                "results": [],
                "total": 0,
                "message": (
                    "No cases found matching your filters. "
                    "Try broadening your search criteria."
                ),
            }

        return {
            "total": total,
            "offset": offset,
            "limit": limit,
            "results": results,
        }

    def get_case(
        self,
        case_id: int = 0,
        slug: str = "",
        full_text: bool = False,
    ) -> dict:
        """Retrieve a full court case by ID or slug.

        Returns complete case metadata and content. Content is truncated at
        30,000 characters by default. Set full_text=True for up to 100,000
        characters.

        Args:
            case_id: Case database ID.
            slug: Case URL slug.
            full_text: Return complete text up to 100k chars (default False).
        """
        qs = Case.objects.filter(review_status="accepted").select_related(
            "court", "court__state"
        )

        case = None
        if case_id:
            case = qs.filter(id=case_id).first()
        elif slug:
            case = qs.filter(slug=slug).first()

        if not case:
            return {
                "error": "Case not found. Provide a valid case_id or slug.",
            }

        content = case.content or ""
        max_len = FULL_TEXT_MAX_LENGTH if full_text else DEFAULT_TRUNCATE_LENGTH
        truncated = len(content) > max_len

        if truncated:
            content = content[:max_len]
            content += (
                f"\n\n[Content truncated at {max_len:,} characters. "
                f"Full text available at {case.get_absolute_url()}]"
            )

        return {
            "id": case.id,
            "slug": case.slug,
            "file_number": case.file_number,
            "date": str(case.date) if case.date else None,
            "type": case.type,
            "ecli": case.ecli,
            "court": {
                "id": case.court.id if case.court else None,
                "name": case.court.name if case.court else None,
                "slug": case.court.slug if case.court else None,
                "state": (
                    case.court.state.name if case.court and case.court.state else None
                ),
            },
            "abstract": case.abstract or "",
            "content": content,
            "content_truncated": truncated,
        }

    def get_case_statistics(
        self,
        court_id: int = 0,
        state: str = "",
        jurisdiction: str = "",
        date_after: str = "",
        date_before: str = "",
        group_by: str = "month",
    ) -> dict:
        """Get aggregated case statistics.

        Returns case counts grouped by time period, optionally filtered
        by court, state, or jurisdiction.

        Args:
            court_id: Filter by court ID.
            state: Filter by state name or slug.
            jurisdiction: Filter by jurisdiction.
            date_after: Count cases from this date (YYYY-MM-DD, default: 1 year ago).
            date_before: Count cases up to this date (YYYY-MM-DD, default: today).
            group_by: Time grouping: "month" (default) or "year".
        """
        qs = Case.objects.filter(review_status="accepted", date__isnull=False)

        if court_id:
            qs = qs.filter(court_id=court_id)
        if state:
            from django.db.models import Q

            qs = qs.filter(
                Q(court__state__name__icontains=state)
                | Q(court__state__slug__iexact=state)
            )
        if jurisdiction:
            qs = qs.filter(court__jurisdiction__icontains=jurisdiction)

        # Default date range: last year
        today = datetime.date.today()
        if date_after:
            try:
                qs = qs.filter(date__gte=datetime.date.fromisoformat(date_after))
            except ValueError:
                pass
        else:
            qs = qs.filter(date__gte=today - datetime.timedelta(days=365))

        if date_before:
            try:
                qs = qs.filter(date__lte=datetime.date.fromisoformat(date_before))
            except ValueError:
                pass

        total = qs.count()

        # Time series
        trunc_fn = TruncYear if group_by == "year" else TruncMonth
        date_format = "%Y" if group_by == "year" else "%Y-%m"

        buckets = (
            qs.annotate(period=trunc_fn("date"))
            .values("period")
            .annotate(count=Count("id"))
            .order_by("period")
        )

        time_series = [
            {"date": b["period"].strftime(date_format), "count": b["count"]}
            for b in buckets
        ]

        # Top courts
        top_courts = (
            qs.values("court__name", "court__slug")
            .annotate(count=Count("id"))
            .order_by("-count")[:10]
        )
        courts_breakdown = [
            {
                "court_name": c["court__name"],
                "court_slug": c["court__slug"],
                "count": c["count"],
            }
            for c in top_courts
        ]

        return {
            "total": total,
            "group_by": group_by,
            "time_series": time_series,
            "top_courts": courts_breakdown,
        }
