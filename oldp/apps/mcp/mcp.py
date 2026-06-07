"""Platform-level MCP tools for OLDP.

Provides discovery tools that help AI agents understand what data is
available on the platform before drilling into specific searches.

The ``get_platform_info`` response is cached in the Django cache for
``PLATFORM_INFO_CACHE_TTL`` seconds because it runs seven aggregate
queries and the underlying counts change slowly.
"""

import logging

from django.conf import settings
from django.core.cache import cache
from mcp_server import MCPToolset

from oldp.apps.cases.models import Case
from oldp.apps.courts.models import Court, State
from oldp.apps.laws.models import Law, LawBook
from oldp.apps.mcp.monitoring import log_tool_call
from oldp.apps.mcp.utils import clamp_limit, with_limit_meta
from oldp.apps.references.models import Reference

logger = logging.getLogger("oldp.mcp.tools")

# get_platform_info runs 7+ aggregate queries; cache the response for a
# few minutes because the underlying counts change very slowly. Override
# via ``MCP_PLATFORM_INFO_CACHE_TTL`` in settings for testing.
_PLATFORM_INFO_CACHE_KEY = "mcp:platform_info:v1"
_DEFAULT_PLATFORM_INFO_CACHE_TTL = 300  # 5 minutes


class PlatformTools(MCPToolset):
    """Platform-level discovery tools for OLDP."""

    @log_tool_call
    def get_platform_info(self) -> dict:
        """Get OLDP platform coverage summary.

        Returns an overview of the data available on the Open Legal Data
        Platform, including counts of cases, laws, courts, and references.
        Call this first to understand what data you can search and retrieve.
        """
        cached = cache.get(_PLATFORM_INFO_CACHE_KEY)
        if cached is not None:
            return cached

        info = self._build_platform_info()
        ttl = getattr(
            settings,
            "MCP_PLATFORM_INFO_CACHE_TTL",
            _DEFAULT_PLATFORM_INFO_CACHE_TTL,
        )
        cache.set(_PLATFORM_INFO_CACHE_KEY, info, ttl)
        return info

    @log_tool_call
    def search_legal(self, query: str, limit: int = 5) -> dict:
        """Search BOTH legislation and court cases in one call.

        Returns the most relevant law sections AND court decisions for the
        query, **grouped by type**. Use this when a legal question may be
        answered by statute or by case law and you don't yet know which —
        e.g. "Eigenbedarf" surfaces § 573 BGB *and* the leading BGH
        decisions together. For type-specific control (citation filters,
        court/date filters), use ``search_cases`` / ``search_laws``.

        Results are grouped rather than merged into one ranked list on
        purpose: court decisions are long and out-score short statute
        texts on relevance, so a naive merged ranking returns only cases
        and buries the on-point law.

        Args:
            query: Search query text (supports Lucene syntax and "phrases").
            limit: Max results per type (default 5, max 25). Values above 25
                are clamped; the response then includes ``limit_clamped:
                true`` and the original ``requested_limit``.
        """
        requested_limit = limit
        limit, limit_was_clamped = clamp_limit(limit, maximum=25)

        from oldp.apps.cases.mcp import _norm_court
        from oldp.apps.search.api import SearchQueryBuilder
        from oldp.apps.search.utils import (
            is_search_backend_error,
            is_search_backend_timeout,
            prepare_search_query,
        )

        normalized = prepare_search_query(query)

        def _snippets(result):
            if getattr(result, "highlighted", None):
                return list(result.highlighted[:3])
            text = getattr(result, "text", "") or ""
            return [text[:200]] if text else []

        def _search(facet):
            builder = SearchQueryBuilder()
            builder.filter_review_status("accepted")
            builder.apply_highlight()
            # The custom SearchBackend drops .models(); the facet clamp is
            # what actually isolates each index (see search_cases/laws).
            sqs = (
                builder.build()
                .auto_query(normalized)
                .filter(facet_model_name_exact=facet)
            )
            return list(sqs[:limit]), sqs

        try:
            law_hits, law_sqs = _search("Law")
            case_hits, case_sqs = _search("Case")
        except Exception as exc:
            logger.warning("mcp_tool_search_failed tool=search_legal error=%s", exc)
            if is_search_backend_timeout(exc):
                return {
                    "error": (
                        "Search timed out while warming caches. "
                        "Retry the same query in a few seconds."
                    ),
                    "retryable": True,
                }
            if is_search_backend_error(exc):
                return {
                    "error": (
                        "Search is temporarily unavailable. "
                        "Try search_cases / search_laws individually."
                    ),
                    "retryable": False,
                }
            raise

        laws = [
            {
                "type": "law",
                "id": int(r.pk),
                "title": getattr(r, "title", ""),
                "book_code": getattr(r, "book_code", ""),
                "slug": getattr(r, "slug", ""),
                "snippets": _snippets(r),
            }
            for r in law_hits
        ]
        cases = [
            {
                "type": "case",
                "id": int(r.pk),
                "title": getattr(r, "title", ""),
                "slug": getattr(r, "slug", ""),
                "date": str(getattr(r, "date", "")),
                "court": _norm_court(getattr(r, "court", "")),
                "decision_type": getattr(r, "decision_type", ""),
                "snippets": _snippets(r),
            }
            for r in case_hits
        ]

        result = {
            "query": query,
            "laws": laws,
            "cases": cases,
            "total_laws": law_sqs.count() if laws else 0,
            "total_cases": case_sqs.count() if cases else 0,
        }
        if not laws and not cases:
            result["message"] = (
                f"No laws or cases found for query '{query}'. "
                "Try different or broader search terms."
            )
        return with_limit_meta(
            result,
            requested=requested_limit,
            applied=limit,
            was_clamped=limit_was_clamped,
            maximum=25,
        )

    @staticmethod
    def _build_platform_info() -> dict:
        """Run the aggregate queries that back ``get_platform_info``.

        Extracted into its own method so it can be tested in isolation and
        so ``get_platform_info`` stays a thin cache wrapper.
        """
        from oldp.apps.cases.mcp import exclude_future_dated_cases

        accepted_cases = Case.objects.filter(review_status="accepted")
        accepted_courts = Court.objects.filter(review_status="accepted")
        latest_books = LawBook.objects.filter(latest=True, review_status="accepted")
        accepted_laws = Law.objects.filter(book__latest=True, review_status="accepted")

        # Exclude future-dated rows from the reported date range so the
        # advertised `latest` doesn't show 2029 entries from broken
        # ingestion.
        date_range = exclude_future_dated_cases(
            accepted_cases.filter(date__isnull=False)
        ).order_by("date")
        earliest = date_range.values_list("date", flat=True).first()
        latest = date_range.values_list("date", flat=True).last()

        states = list(
            State.objects.filter(court__review_status="accepted")
            .distinct()
            .values_list("name", flat=True)
        )

        return {
            "platform": "Open Legal Data Platform (OLDP)",
            "description": (
                "German legal data including court decisions and legislation "
                "with cross-references. All data is public open data."
            ),
            "website": getattr(settings, "SITE_URL", "https://de.openlegaldata.io"),
            "data_coverage": {
                "total_cases": accepted_cases.count(),
                "total_courts": accepted_courts.count(),
                "total_law_books": latest_books.count(),
                "total_law_sections": accepted_laws.count(),
                "total_references": Reference.objects.count(),
                "case_date_range": {
                    "earliest": str(earliest) if earliest else None,
                    "latest": str(latest) if latest else None,
                },
                "states": states,
            },
            "available_tools": {
                "discovery": [
                    "get_platform_info",
                    "list_courts",
                    "list_law_books",
                ],
                "search": [
                    "search_legal (laws + cases together, grouped by type)",
                    "search_cases (full-text via Elasticsearch)",
                    "search_laws (full-text via Elasticsearch)",
                    "filter_cases (structured ORM filtering)",
                    "get_similar_cases (cases similar to a given case)",
                ],
                "retrieval": [
                    "get_case (full case text, truncated at 30k chars by default)",
                    "get_law_section (law text by book code + section)",
                    "get_court (detailed court info)",
                ],
                "cross_references": [
                    "validate_citation (check Aktenzeichen, ECLI, or law ref)",
                    "get_case_references (what does a case cite?)",
                    "get_citing_cases (what cases cite a given case?)",
                    "get_cases_for_law (cases interpreting a statute section)",
                ],
                "statistics": [
                    "get_case_statistics (aggregated counts by court/year)",
                ],
            },
            "disclaimer": (
                "This data is provided for informational purposes only and is "
                "not a substitute for professional legal advice. References are "
                "automatically extracted and may be incomplete."
            ),
        }
