"""Utility helpers for the search app."""


def parse_citation_params(params):
    """Parse citation query params into ``(kind, token)`` or ``None``.

    Lightweight counterpart to ``_resolve_citation_filter`` in the search
    view: only does the parsing + token construction, no DB lookup for a
    display label. Used by every surface that filters by citation (web
    form, REST ``SearchFilter``, MCP ``search_cases``) so the param
    parsing lives in exactly one place.

    Args:
        params: A mapping-like object (``request.GET``,
            ``request.query_params``, or a plain ``dict``) exposing
            ``cited_law_book`` + ``cited_law_section`` or ``cited_case``.

    Returns:
        ``("law", "<book_slug>__<section_slug>")`` when both law params
        are present, ``("case", "<pk>")`` when ``cited_case`` is a valid
        int, otherwise ``None``.
    """
    from oldp.apps.cases.search_indexes import cited_law_token

    book = (params.get("cited_law_book") or "").strip()
    section = (params.get("cited_law_section") or "").strip()
    case = (params.get("cited_case") or "").strip()
    if book and section:
        return ("law", cited_law_token(book, section))
    if case:
        try:
            return ("case", str(int(case)))
        except ValueError:
            return None
    return None


def apply_citation_filter(queryset, params):
    """Chain a citation filter onto ``queryset`` if citation params are set.

    Convenience wrapper used by both the web form and the REST filter
    backend. Returns the queryset unchanged if no citation params are
    present, otherwise applies ``.filter(cited_laws=…)`` or
    ``.filter(cited_cases=…)`` plus the ``facet_model_name_exact="Case"``
    clamp (the citation fields only exist on the Case index).
    """
    citation = parse_citation_params(params)
    if citation is None:
        return queryset
    kind, token = citation
    if kind == "law":
        queryset = queryset.filter(cited_laws=token)
    else:
        queryset = queryset.filter(cited_cases=token)
    return queryset.filter(facet_model_name_exact="Case")


def is_search_backend_error(exc: Exception) -> bool:
    """Check if an exception is an Elasticsearch connection/transport error."""
    try:
        from elasticsearch.exceptions import ConnectionError, TransportError

        return isinstance(exc, (ConnectionError, TransportError))
    except ImportError:
        return False


def citing_cases_queryset_via_es(field: str, value: str, max_results: int = 10000):
    """Return ``(case_queryset, total)`` for cases citing ``value``.

    Variant of :func:`citing_cases_via_es` for callers that need a
    Django ``QuerySet`` (REST pagination, MCP slicing) rather than a
    pre-materialised list:

      * Issues one ES query to resolve the matching case IDs (in
        ``-date`` order, capped at ``max_results``) and the total
        count;
      * Builds a Django queryset filtered to those IDs, with
        ``select_related("court")`` + ``defer(*defer_fields_list_view)``
        and re-applies ``order_by("-date")`` so paginator slices land
        in the same order as ES emitted;
      * **Raises** ``ConnectionError`` / ``ConnectionTimeout`` /
        ``TransportError`` on ES failure — the API translates these to
        ``SearchBackendUnavailable`` / ``SearchBackendTimeout`` (DRF
        503 + retry hint) and MCP translates them to its
        ``{error, retryable, hint}`` dict.

    ``max_results`` caps the materialised id list to bound memory.
    With ``PAGINATE_UNTIL * page_size_max = 10 * 1000 = 10_000`` for
    the small-results paginator this is also the upper bound the
    API can ever surface, so anything above it would be unreachable.
    """
    from haystack.query import SearchQuerySet

    from oldp.apps.cases.models import Case

    sqs = (
        SearchQuerySet()
        .filter(**{field: value})
        .filter(facet_model_name="Case")
        .filter(review_status="accepted")
        .order_by("-date")
    )
    total = sqs.count()
    if total == 0:
        return Case.objects.none(), 0

    # Materialise the matching case ids in ES sort order. We don't use
    # ``load_all()`` here — DRF's paginator will slice the Django
    # queryset and hydrate the page itself, so pre-fetching all
    # ``max_results`` cases would waste cycles.
    case_ids = [int(r.pk) for r in sqs[:max_results]]
    if not case_ids:
        return Case.objects.none(), 0

    qs = (
        Case.objects.filter(id__in=case_ids, review_status="accepted")
        .select_related("court")
        .defer(*Case.defer_fields_list_view)
        .order_by("-date")
    )
    return qs, total


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
