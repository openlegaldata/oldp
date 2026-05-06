"""MCP tools for case search, filtering, retrieval, and statistics."""

import datetime
import logging

from django.db.models import Count, Q
from django.db.models.functions import TruncMonth, TruncYear
from mcp_server import MCPToolset

from oldp.apps.cases.models import Case
from oldp.apps.courts.mcp import resolve_jurisdiction
from oldp.apps.mcp.monitoring import log_tool_call

logger = logging.getLogger("oldp.mcp.tools")

# Maximum content length returned by default
DEFAULT_TRUNCATE_LENGTH = 30000
FULL_TEXT_MAX_LENGTH = 100000

# Some upstream extractors mis-parse dates and produce case records
# whose `date` is years in the future (test report shows 2026 / 2027 /
# 2029 entries appearing in a 2024 deploy — docs/mcp-test-report.md
# issue #8). Filter those out at the MCP boundary so consumers never
# see polluted aggregates, ordered lists, or "newest" results.
# A small grace period accommodates embargoed publications.
MAX_FUTURE_DAYS = 14


def _future_date_cutoff():
    return datetime.date.today() + datetime.timedelta(days=MAX_FUTURE_DAYS)


def exclude_future_dated_cases(qs, date_field="date"):
    """Drop cases whose date is more than MAX_FUTURE_DAYS in the future.

    The single-case retrieval tool (`get_case`) deliberately does NOT
    use this — if a user asks for a specific id they should see what's
    in the database. Use this for listings, aggregates, and citation
    walks where the bogus rows just pollute results.
    """
    return qs.filter(**{f"{date_field}__lte": _future_date_cutoff()})


class CaseTools(MCPToolset):
    """Tools for searching, filtering, and retrieving court cases."""

    @log_tool_call
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

            # Constrain to the Case index. The custom SearchBackend silently
            # drops the .models() filter applied via filter_models above, so
            # without this guard a query that also matches Law text (e.g.
            # "Schadensersatz") would leak Law results. Mirrors the pattern
            # in SearchSchemaFilter used by the REST API.
            sqs = sqs.filter(facet_model_name_exact="Case")

            # Hide cases with bogus future dates (issue #8). Applied
            # against the Haystack `date` field, which is mirrored from
            # Case.date by CaseIndex.prepare_date.
            sqs = sqs.filter(date__lte=_future_date_cutoff())

            if court_code:
                sqs = sqs.filter(court_exact=court_code)
            if decision_type:
                sqs = sqs.filter(decision_type_exact=decision_type)

            # Materialise the limited slice first. If it's empty we skip the
            # total-count round-trip entirely; otherwise we ask ES for the
            # total once.
            sliced = list(sqs[:limit])
            if not sliced:
                return {
                    "results": [],
                    "total": 0,
                    "message": (
                        f"No cases found for query '{query}'. "
                        "Try different search terms or broader filters."
                    ),
                }

            results = []
            for result in sliced:
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
            return {"total": total, "results": results}

        except Exception as exc:
            logger.warning("mcp_tool_search_failed tool=search_cases error=%s", exc)
            return {
                "error": (
                    "Search is temporarily unavailable. Use filter_cases "
                    "for structured queries instead."
                ),
            }

    @log_tool_call
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

        qs = exclude_future_dated_cases(
            Case.objects.filter(review_status="accepted").select_related("court")
        )

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

        # Fetch one extra row so we can detect "has more" without issuing a
        # second COUNT(*) scan when the result set happens to fit in a single
        # page. A full COUNT(*) only runs on boundary slices.
        sliced = list(qs[offset : offset + limit + 1])
        has_more = len(sliced) > limit
        page = sliced[:limit]

        if not page:
            return {
                "results": [],
                "total": 0,
                "message": (
                    "No cases found matching your filters. "
                    "Try broadening your search criteria."
                ),
            }

        if has_more:
            # More pages remain; caller may want to know total for pagination UI.
            total = qs.count()
        else:
            total = offset + len(page)

        results = []
        for case in page:
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

        return {
            "total": total,
            "offset": offset,
            "limit": limit,
            "results": results,
        }

    @log_tool_call
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

    @log_tool_call
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
            jurisdiction: Filter by jurisdiction. Accepts the English
                shortcuts ("ordinary", "labor", …) or the stored German
                values ("Ordentliche Gerichtsbarkeit", …).
            date_after: Count cases from this date (YYYY-MM-DD, default: 1 year ago).
            date_before: Count cases up to this date (YYYY-MM-DD, default: today).
            group_by: Time grouping: "month" (default) or "year".
        """
        qs = exclude_future_dated_cases(
            Case.objects.filter(review_status="accepted", date__isnull=False)
        )

        if court_id:
            qs = qs.filter(court_id=court_id)
        if state:
            qs = qs.filter(
                Q(court__state__name__icontains=state)
                | Q(court__state__slug__iexact=state)
            )
        if jurisdiction:
            qs = qs.filter(
                court__jurisdiction__icontains=resolve_jurisdiction(jurisdiction)
            )

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

        # Compute the time-series aggregation once and derive the total from
        # its buckets (avoiding a separate COUNT(*) scan on the same filtered
        # rows). The top-courts aggregation stays a separate query because
        # its GROUP BY is on a different dimension.
        trunc_fn = TruncYear if group_by == "year" else TruncMonth
        date_format = "%Y" if group_by == "year" else "%Y-%m"

        buckets = list(
            qs.annotate(period=trunc_fn("date"))
            .values("period")
            .annotate(count=Count("id"))
            .order_by("period")
        )

        total = sum(b["count"] for b in buckets)
        time_series = [
            {"date": b["period"].strftime(date_format), "count": b["count"]}
            for b in buckets
        ]

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
