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
                    "search_cases (full-text via Elasticsearch)",
                    "search_laws (full-text via Elasticsearch)",
                    "filter_cases (structured ORM filtering)",
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
