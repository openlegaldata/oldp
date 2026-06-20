"""Utility helpers for the search app."""

# Map of typographic double-quote characters to ASCII ``"``. German legal
# text routinely uses „…" (Gänsefüßchen) or »…« guillemets, and users
# pasting a quoted passage from a PDF / Word / a court website get these
# instead of the ASCII ``"`` that Haystack's ``AutoQuery`` needs to detect
# an exact-phrase query. Without normalization the phrase silently
# degrades to an implicit-AND term query (see search-improvements.md §C
# failure mode 2). Guillemets map to ``"`` regardless of direction —
# AutoQuery only pairs ``"`` characters, so open/close orientation is
# irrelevant for phrase detection.
_TYPOGRAPHIC_QUOTES = {
    "„": '"',  # „ double low-9 quotation mark (German opening)
    "“": '"',  # " left double quotation mark
    "”": '"',  # " right double quotation mark
    "‟": '"',  # ‟ double high-reversed-9 quotation mark
    "«": '"',  # « left-pointing double angle quotation mark
    "»": '"',  # » right-pointing double angle quotation mark
    "″": '"',  # ″ double prime
    "＂": '"',  # ＂ fullwidth quotation mark
}

_QUOTE_TRANSLATION = str.maketrans(_TYPOGRAPHIC_QUOTES)


def normalize_search_query(text):
    """Normalize a raw search query before it reaches Haystack's AutoQuery.

    Maps typographic / "smart" double-quote characters to ASCII ``"`` so
    exact-phrase queries survive a copy-paste from formatted sources.
    Applied uniformly at every keyword entry point (web form, REST
    ``SearchFilter``, MCP ``search_cases`` / ``search_laws``) so all
    surfaces share one definition of what a query means.

    Args:
        text: The raw user query string (may be ``None``).

    Returns:
        The normalized query string (empty string if ``text`` is falsy).
    """
    if not text:
        return ""
    return text.translate(_QUOTE_TRANSLATION)


# German function-word stoplist (articles, pronouns, possessives, auxiliary
# and modal verbs, conjunctions, prepositions, question words, particles).
# Deliberately function words ONLY — no content nouns/adjectives — so
# stripping never drops a discriminative legal term. Used to rescue
# natural-language queries: laypersons on legal-advice sites type whole
# questions ("Welche Frist habe ich für den Einspruch gegen den
# Bußgeldbescheid"), and with AND-default every word — incl. ``welche``,
# ``habe``, ``ich``, ``für``, ``den`` — must match, collapsing the result
# set. Removing the function words leaves the content terms (``Frist
# Einspruch Bußgeldbescheid``) so AND stays precise but actually returns.
_GERMAN_QUERY_STOPWORDS = frozenset(
    """
    der die das den dem des ein eine einer eines einem einen kein keine
    ich du er sie es wir ihr mich dich mir dir uns euch ihm ihn ihnen
    mein meine meiner meines deine sein seine ihre unser euer
    und oder aber sondern denn doch sowie bzw beziehungsweise
    dass daß weil wenn falls als ob damit obwohl während indem
    wie was wann wo woher wohin warum wieso weshalb welche welcher welches
    welchem welchen wer wessen wem wen
    ist sind war waren bin bist seid sei gewesen
    habe hast hat haben hatte hatten hattest gehabt
    werde wirst wird werden wurde wurden worden
    kann kannst koennen können konnte konnten muss musst müssen musste
    soll sollst sollen sollte will willst wollen wollte darf dürfen mag
    fuer für gegen ohne um durch bei mit nach von vom aus zu zur zum
    an am auf in im ins unter ueber über vor hinter neben zwischen seit bis
    nicht auch nur noch schon sehr mehr man dann also so dies diese dieser
    dieses jener jene meinem meinen
    """.split()
)


def strip_query_stopwords(text):
    """Drop German function words from the *bare-term* part of a query.

    Leaves intact: anything inside double quotes (exact phrases), tokens
    carrying Lucene operators (``+`` / ``-`` prefixes, ``field:value``,
    wildcards ``* ?``), and the uppercase boolean operators
    ``AND`` / ``OR`` / ``NOT``. Only plain stopword tokens outside quotes
    are removed.

    Safety: if removal would leave no bare terms *and* the query has no
    quoted phrase, the original text is returned unchanged — better to run
    the user's literal query than to match everything.

    Args:
        text: A query string (ideally already quote-normalized).

    Returns:
        The query with bare German stopwords removed.
    """
    if not text or not text.strip():
        return text or ""

    def _strip_tokens(segment, out, state):
        """Append non-stopword tokens of ``segment`` to ``out``."""
        for tok in segment.split():
            is_operator = tok in ("AND", "OR", "NOT")
            is_special = tok.startswith(("+", "-")) or any(
                ch in tok for ch in ':*?()^~"'
            )
            # Compare against the stoplist ignoring surrounding punctuation
            # (so "den," / "(ich)" are recognised) but never strip tokens
            # carrying Lucene operators or the boolean keywords.
            core = tok.strip(".,;:!?…„“”«»").lower()
            if not is_operator and not is_special and core in _GERMAN_QUERY_STOPWORDS:
                continue
            out.append(tok)
            if not is_operator:
                state["kept"] = True

    out = []
    state = {"kept": False}

    # An odd number of quote chars means the phrase is unbalanced. Don't
    # phrase-split (that would silently auto-close the dangling quote into
    # an exact phrase); strip token-wise instead, leaving the stray quote
    # in place for AutoQuery to drop.
    if text.count('"') % 2 == 1:
        _strip_tokens(text, out, state)
        return " ".join(out) if state["kept"] else text

    # Balanced: split into alternating non-quote / quoted segments. Odd
    # indices are the contents between paired double quotes (kept verbatim
    # as phrases).
    parts = text.split('"')
    has_phrase = len(parts) >= 3
    for i, part in enumerate(parts):
        if i % 2 == 1:
            out.append('"' + part + '"')  # quoted phrase, verbatim
        else:
            _strip_tokens(part, out, state)

    if not state["kept"] and not has_phrase:
        return text  # all-stopword query — don't reduce to nothing

    return " ".join(out)


def prepare_search_query(text):
    """Full pre-processing applied to every keyword query before AutoQuery.

    Normalizes typographic quotes (so pasted phrases match) and strips
    German function words from bare terms (so natural-language questions
    return precise results instead of collapsing under AND-default). One
    helper so the web form, REST ``SearchFilter``, and the MCP search
    tools all interpret a query identically.

    Args:
        text: The raw user query string (may be ``None``).

    Returns:
        The prepared query string (empty string if ``text`` is falsy).
    """
    return strip_query_stopwords(normalize_search_query(text))


def narrow_to_model(sqs, facet_model_name):
    """Isolate ``sqs`` to one Haystack model via a FILTER-context narrow.

    The custom ``SearchBackend`` ignores ``SearchQuerySet.models()``, so
    every keyword-search call site has to clamp the index itself. Do it with
    ``.narrow`` — which the backend turns into a non-scoring ``bool.filter``
    ``query_string`` clause — rather than ``.filter(facet_model_name_exact=…)``,
    which Haystack serialises into the main *scoring* query string. Two
    reasons:

    * **Exact-match boost.** The backend ranks an exact navigational target
      (``"bgb 123"`` → § 123 BGB; a file number → its case) via a
      ``match_phrase`` on ``exact_matches``, keyed off the *bare* user query.
      Keeping the model/status clamp out of the main query string keeps that
      query bare; with the clamp serialised in (``… AND
      facet_model_name_exact:Law``) the ``match_phrase`` query is polluted
      with the filter expression and never matches, so the on-point doc was
      missing from REST / MCP results while the web UI (which applies no such
      clamp) ranked it #1.
    * **Leak-safety.** The exact-match boost is a ``should`` *alternative*.
      If the model clamp were also a ``should`` (scoring) clause, a Law doc
      that matched only the boost could be returned from a Case-only search.
      As a ``bool.filter`` the clamp is mandatory and the boost cannot bypass
      it.

    Mirrors the ``.narrow`` the web faceted search already uses for facet
    selections.
    """
    return sqs.narrow('facet_model_name_exact:"%s"' % facet_model_name)


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

    Convenience wrapper used by the web form, REST filter backend, and
    MCP ``search_cases``. Returns the queryset unchanged if no citation
    params are present, otherwise applies ``.filter(cited_laws=…)`` or
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


def citing_cases_queryset_via_es(
    field: str, value: str, max_results: int = 10000, order_by: str = "-date"
):
    """Return ``(case_queryset, total)`` for cases citing ``value``.

    ``order_by`` controls the sort applied both to the ES id resolution
    and the hydrated Django queryset so the two stay aligned — default
    ``-date`` (newest first); pass ``-citing_cases_count`` for
    most-cited / landmark-interpretation first.

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
        .order_by(order_by)
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
        .order_by(order_by)
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
