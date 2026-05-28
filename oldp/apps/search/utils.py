"""Utility helpers for the search app."""


def is_search_backend_error(exc: Exception) -> bool:
    """Check if an exception is an Elasticsearch connection/transport error."""
    try:
        from elasticsearch.exceptions import ConnectionError, TransportError

        return isinstance(exc, (ConnectionError, TransportError))
    except ImportError:
        return False


def citing_cases_via_es(field: str, value: str, limit: int = 10):
    """Look up cases citing ``value`` in the given ``cited_*`` field.

    ``field`` is the name of the multi-value field on ``CaseIndex``
    (``"cited_laws"`` for a law section, ``"cited_cases"`` for a case).
    ``value`` is the corresponding token: ``"book_slug__section_slug"``
    for laws, the cited case's PK as a string for cases.

    Returns ``(cases_list, total_count, error_message)``. ``cases_list``
    is a list of ``Case`` model instances hydrated via Haystack's
    ``load_all`` (one batched SQL fetch with the index's
    ``read_queryset`` ``select_related`` chain). On ES failure we set
    ``error_message`` to a user-facing string and leave the list
    empty — callers (the law and case detail views) render this as a
    "search unavailable" notice with a deep link to the full search
    results page instead of falling back to the SQL JOIN path.
    """
    from haystack.query import SearchQuerySet

    try:
        sqs = (
            SearchQuerySet()
            .filter(**{field: value})
            .filter(facet_model_name="Case")
            .filter(review_status="accepted")
            .order_by("-date")
            .load_all()
        )
        total = sqs.count()
        results = list(sqs[:limit])
    except Exception as exc:
        if is_search_backend_error(exc):
            import logging

            from django.utils.translation import gettext_lazy as _

            logger = logging.getLogger(__name__)
            logger.warning(
                "Citing-cases ES lookup failed (%s=%r, timeout=%s): %s",
                field,
                value,
                is_search_backend_timeout(exc),
                exc,
            )
            return (
                [],
                None,
                _(
                    "Search backend is currently unavailable, so the list "
                    "of citing cases cannot be loaded. Please try again "
                    "later."
                ),
            )
        raise

    # ``r.object`` is None when the ES doc points to a row that
    # ``CaseIndex.read_queryset`` no longer returns (deleted case,
    # ``review_status`` flipped after indexing). Drop those rather
    # than rendering a hole in the table.
    cases = [r.object for r in results if getattr(r, "object", None) is not None]
    return cases, total, None


def is_search_backend_timeout(exc: Exception) -> bool:
    """Subset of :func:`is_search_backend_error` for transient timeouts.

    A timeout is recoverable on retry — once ES has read the relevant
    segment files into the OS page cache, the same query returns
    sub-100ms. Distinguishing this from a true outage lets MCP / web
    callers surface a ``retryable`` hint instead of asking the user to
    give up.

    Covers:
      * elasticsearch-py ``ConnectionTimeout``;
      * ``TransportError`` subclasses whose status implies a timeout
        (504 from a gateway, 408 from ES itself);
      * nested causes (urllib3 ``ReadTimeoutError`` etc.) reached via
        ``__cause__``.
    """
    try:
        from elasticsearch.exceptions import (
            ConnectionTimeout,
            TransportError,
        )
    except ImportError:
        return False
    if isinstance(exc, ConnectionTimeout):
        return True
    if isinstance(exc, TransportError):
        status = getattr(exc, "status_code", None)
        if status in (408, 504):
            return True
    cause = getattr(exc, "__cause__", None)
    if cause is not None and cause is not exc:
        return is_search_backend_timeout(cause)
    return False
