"""MCP tools for law book discovery, law section retrieval, and search."""

import logging

from django.db.models import Count, Q
from mcp_server import MCPToolset

from oldp.apps.laws.models import Law, LawBook
from oldp.apps.mcp.monitoring import log_tool_call

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
            limit: Maximum results (default 50, max 200).
        """
        limit = min(max(1, limit), 200)
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

        annotated = qs.annotate(section_count=Count("law")).order_by("-section_count")

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
            return {
                "results": [],
                "total": 0,
                "message": "No law books found. Try broadening your search.",
            }

        return {"total": total, "results": results}

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
            section: Section identifier (e.g. "823", "1", "242").
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
                return {
                    "error": f"Law book '{book_code}' not found. Use list_law_books to see available books.",
                }
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
            limit: Maximum results (default 10, max 50).
        """
        limit = min(max(1, limit), 50)

        try:
            from oldp.apps.search.api import SearchQueryBuilder

            builder = SearchQueryBuilder()
            builder.filter_models([Law])
            builder.filter_review_status("accepted")
            builder.apply_highlight()
            sqs = builder.build().auto_query(query)

            if book_code:
                sqs = sqs.filter(book_code=book_code.upper())

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
                        "id": result.pk,
                        "title": getattr(result, "title", ""),
                        "book_code": getattr(result, "book_code", ""),
                        "slug": getattr(result, "slug", ""),
                        "snippets": snippets,
                    }
                )

            if not results:
                return {
                    "results": [],
                    "total": 0,
                    "message": f"No laws found for query '{query}'. Try different search terms.",
                }

            # Single ES count round-trip, only if we got results.
            total = sqs.count()
            return {"total": total, "results": results}

        except Exception as exc:
            logger.warning("mcp_tool_search_failed tool=search_laws error=%s", exc)
            return {
                "error": (
                    "Search is temporarily unavailable. Use get_law_section "
                    "with book_code and section to retrieve specific law text."
                ),
            }
