"""MCP tools for law book discovery, law section retrieval, and search."""

import logging

from django.db.models import Count, Q
from mcp_server import MCPToolset

from oldp.apps.laws.models import Law, LawBook
from oldp.apps.mcp.monitoring import log_tool_call
from oldp.apps.mcp.utils import clamp_limit, with_limit_meta

logger = logging.getLogger("oldp.mcp.tools")


class LawTools(MCPToolset):
    """Tools for browsing law books, searching laws, and retrieving law text."""

    @log_tool_call
    def list_law_books(
        self,
        latest_only: bool = True,
        search: str = "",
        limit: int = 50,
    ) -> dict:
        """List available German law books (e.g. BGB, StGB, GG).

        Returns law books with their codes, titles, and section counts.
        Use this to discover what legislation is available before searching
        for specific law sections.

        Args:
            latest_only: Only show latest revisions (default True).
            search: Search book codes and titles.
            limit: Maximum results (default 50, max 200). Values above 200
                are clamped; the response then includes
                ``limit_clamped: true`` and the original ``requested_limit``.
        """
        requested_limit = limit
        limit, limit_was_clamped = clamp_limit(limit, maximum=200)
        qs = LawBook.objects.filter(review_status="accepted")

        if latest_only:
            qs = qs.filter(latest=True)
        if search:
            # Apply the OR filter in a single .filter() call so SQL produces
            # one WHERE (code ILIKE %s OR title ILIKE %s) instead of the
            # previous form which chained queryset | queryset and sometimes
            # re-joined the base relation.
            qs = qs.filter(Q(code__icontains=search) | Q(title__icontains=search))

        # Count the matching books using the un-annotated queryset to avoid
        # a GROUP BY over the (potentially large) Law table. The annotated
        # queryset is only used for the limited result slice.
        total = qs.count()

        # Count only accepted Law rows so the section_count matches what
        # get_law_section / search_laws will actually return (they both
        # filter on review_status="accepted"). Without this filter the
        # section_count would advertise pending / rejected rows that
        # callers cannot retrieve.
        annotated = qs.annotate(
            section_count=Count("law", filter=Q(law__review_status="accepted"))
        ).order_by("-section_count")

        results = []
        for book in annotated[:limit]:
            results.append(
                {
                    "id": book.id,
                    "code": book.code,
                    "title": book.title,
                    "slug": book.slug,
                    "revision_date": str(book.revision_date),
                    "latest": book.latest,
                    "section_count": book.section_count,
                }
            )

        if not results:
            return with_limit_meta(
                {
                    "results": [],
                    "total": 0,
                    "message": "No law books found. Try broadening your search.",
                },
                requested=requested_limit,
                applied=limit,
                was_clamped=limit_was_clamped,
                maximum=200,
            )

        return with_limit_meta(
            {"total": total, "results": results},
            requested=requested_limit,
            applied=limit,
            was_clamped=limit_was_clamped,
            maximum=200,
        )

    @log_tool_call
    def get_law_section(
        self,
        book_code: str = "",
        section: str = "",
        law_id: int = 0,
    ) -> dict:
        """Get the full text of a specific law section.

        Retrieve law text by book code and section number, or by law ID.
        For example, get_law_section(book_code="BGB", section="823") returns
        the text of section 823 of the German Civil Code.

        Args:
            book_code: Law book code (e.g. "BGB", "StGB", "GG").
            section: Section identifier. Accept bare numbers ("823",
                "1", "242") or fully-qualified strings ("§ 823",
                "Art. 14", "Artikel 1") — the lookup tries the bare
                form first and then the common prefixed variants. The
                ``section`` field on the response is whatever the DB
                stores, which differs by book convention: BGB / StGB /
                ZPO etc. store ``§ N`` (e.g. ``"§ 823"``), the
                Grundgesetz stores ``Art N`` (e.g. ``"Art 1"``).
            law_id: Direct law database ID (alternative to book_code+section).
        """
        law = None

        if law_id:
            law = (
                Law.objects.filter(id=law_id, review_status="accepted")
                .select_related("book")
                .first()
            )
        elif book_code and section:
            book = LawBook.objects.filter(
                code__iexact=book_code,
                latest=True,
                review_status="accepted",
            ).first()
            if not book:
                from oldp.apps.laws.suggestions import suggest_book_codes

                error = {
                    "error": f"Law book '{book_code}' not found. Use list_law_books to see available books.",
                }
                suggestions = suggest_book_codes(book_code)
                if suggestions:
                    error["suggestions"] = suggestions
                return error
            law = (
                Law.objects.filter(
                    book=book,
                    review_status="accepted",
                )
                .filter(section__iexact=section)
                .select_related("book")
                .first()
            )
            if not law:
                # Try partial match
                law = (
                    Law.objects.filter(
                        book=book,
                        review_status="accepted",
                        section__icontains=section,
                    )
                    .select_related("book")
                    .first()
                )
        else:
            return {
                "error": "Provide either law_id, or both book_code and section.",
            }

        if not law:
            return {
                "error": f"Law section not found for book='{book_code}', section='{section}'.",
            }

        return {
            "id": law.id,
            "book_code": law.book.code,
            "book_title": law.book.title,
            "section": law.section,
            "title": law.title,
            "slug": law.slug,
            "content": law.content,
            "amtabk": law.amtabk or "",
            "kurzue": law.kurzue or "",
        }

    @log_tool_call
    def search_laws(
        self,
        query: str,
        book_code: str = "",
        limit: int = 10,
    ) -> dict:
        """Full-text search across law sections via Elasticsearch.

        Returns matching law sections with highlighted snippets. Does NOT
        return full text - use get_law_section to retrieve the complete
        content of a specific section.

        Args:
            query: Search query text (supports Lucene syntax).
            book_code: Optional filter by law book code (e.g. "BGB").
            limit: Maximum results (default 10, max 50). Values above 50 are
                clamped; the response then includes ``limit_clamped: true``
                and the original ``requested_limit``.
        """
        requested_limit = limit
        limit, limit_was_clamped = clamp_limit(limit, maximum=50)

        try:
            from oldp.apps.search.api import SearchQueryBuilder
            from oldp.apps.search.utils import normalize_search_query

            builder = SearchQueryBuilder()
            builder.filter_models([Law])
            builder.filter_review_status("accepted")
            builder.apply_highlight()
            sqs = builder.build().auto_query(normalize_search_query(query))

            # Constrain to the Law index. The custom SearchBackend silently
            # drops the .models() filter applied via filter_models above, so
            # without this guard the query also matches Case documents.
            # Mirrors the pattern in SearchSchemaFilter used by the REST API.
            sqs = sqs.filter(facet_model_name_exact="Law")

            if book_code:
                sqs = sqs.filter(book_code_exact=book_code.upper())

            # Materialise the limited slice first so we can return results
            # without triggering a second ES round-trip when the caller
            # doesn't need a total.
            sliced = list(sqs[:limit])
            results = []
            for result in sliced:
                snippets = []
                if hasattr(result, "highlighted") and result.highlighted:
                    snippets = result.highlighted[:3]
                elif hasattr(result, "text") and result.text:
                    snippets = [result.text[:200]]

                results.append(
                    {
                        # result.pk is a string from ES; cast to int so
                        # downstream MCP/REST consumers can pass this id
                        # back into get_law_section(law_id=…) /
                        # get_cases_for_law(law_id=…) without a type
                        # error. Django Law PK is the source of truth.
                        "id": int(result.pk),
                        "title": getattr(result, "title", ""),
                        "book_code": getattr(result, "book_code", ""),
                        "slug": getattr(result, "slug", ""),
                        "snippets": snippets,
                    }
                )

            if not results:
                return with_limit_meta(
                    {
                        "results": [],
                        "total": 0,
                        "message": f"No laws found for query '{query}'. Try different search terms.",
                    },
                    requested=requested_limit,
                    applied=limit,
                    was_clamped=limit_was_clamped,
                    maximum=50,
                )

            # Single ES count round-trip, only if we got results.
            total = sqs.count()
            return with_limit_meta(
                {"total": total, "results": results},
                requested=requested_limit,
                applied=limit,
                was_clamped=limit_was_clamped,
                maximum=50,
            )

        except Exception as exc:
            from oldp.apps.search.utils import is_search_backend_timeout

            logger.warning("mcp_tool_search_failed tool=search_laws error=%s", exc)
            if is_search_backend_timeout(exc):
                return {
                    "error": (
                        "Search timed out while warming caches. "
                        "Retry the same query in a few seconds."
                    ),
                    "retryable": True,
                    "hint": (
                        "First-touch queries on large result sets read "
                        "ES segments from disk; the same query is "
                        "sub-100ms on the next attempt."
                    ),
                }
            return {
                "error": (
                    "Search is temporarily unavailable. Use get_law_section "
                    "with book_code and section to retrieve specific law text."
                ),
                "retryable": False,
            }
