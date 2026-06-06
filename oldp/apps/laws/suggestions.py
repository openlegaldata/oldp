"""Fuzzy ``did_you_mean`` suggestions for law-book codes.

When a caller (REST, MCP, or an LLM agent) asks for a law book that does
not exist — a typo like ``BGBB``, a guess like ``DSGVOO``, or a wrong
casing — a bare "not found" is a dead end. These helpers return the
closest *existing* book codes so the error can carry a recovery hint
(see B10 in ``search-improvements.md``).

The matching logic is split out as a pure function so it can be unit
tested without touching the database.
"""

import difflib


def closest_codes(code, candidates, limit=5):
    """Return up to ``limit`` codes from ``candidates`` closest to ``code``.

    Pure (no DB). Combines two cheap signals, both case-insensitive:

    1. **Prefix matches** — an existing code that starts with the query, or
       a query that starts with an existing code (catches ``DSGVOO`` →
       ``DSGVO`` and ``BGB`` → ``BGBEG``). Ranked shortest-first.
    2. **Edit-distance matches** via :func:`difflib.get_close_matches`
       (catches transpositions / single-char typos like ``StPOO``).

    Prefix matches come first (a strong signal for code lookups), then
    edit-distance matches, de-duplicated, preserving the original casing
    of the candidate.

    Args:
        code: The (wrong) code the caller asked for.
        candidates: Iterable of existing book codes.
        limit: Maximum number of suggestions to return.

    Returns:
        A list of suggested codes (original casing), best first.
    """
    query = (code or "").strip().upper()
    # A 1-char query would prefix-match nearly every code — too noisy to be a
    # useful "did you mean", so bail out.
    if len(query) < 2:
        return []

    # Map upper-case form -> first-seen original, to dedupe case/revision
    # variants while keeping a presentable code.
    by_upper = {}
    for c in candidates:
        cu = (c or "").strip().upper()
        if cu and cu != query and cu not in by_upper:
            by_upper[cu] = c

    prefix = sorted(
        (cu for cu in by_upper if cu.startswith(query) or query.startswith(cu)),
        key=lambda cu: (len(cu), cu),
    )

    fuzzy = difflib.get_close_matches(query, list(by_upper), n=limit * 2, cutoff=0.6)

    ordered = []
    for cu in prefix + fuzzy:
        original = by_upper[cu]
        if original not in ordered:
            ordered.append(original)
        if len(ordered) >= limit:
            break
    return ordered


def suggest_book_codes(code, limit=5):
    """Suggest existing law-book codes close to ``code`` (DB-backed).

    Queries distinct accepted ``LawBook`` codes and delegates ranking to
    :func:`closest_codes`. Intended for "law book not found" error paths,
    which are rare, so the un-cached ``DISTINCT`` scan is acceptable.

    Args:
        code: The (wrong) book code that was not found.
        limit: Maximum number of suggestions.

    Returns:
        A list of suggested codes, best first (possibly empty).
    """
    from oldp.apps.laws.models import LawBook

    # Mirror the lookups' ``latest=True`` filter: suggesting a code that only
    # exists as a historical revision would point the caller at something the
    # tool's own (latest-only) lookup still refuses to resolve. ``latest`` is
    # also part of the ``(code, latest)`` index, so this scans far fewer rows.
    candidates = (
        LawBook.objects.filter(review_status="accepted", latest=True)
        .values_list("code", flat=True)
        .distinct()
    )
    return closest_codes(code, candidates, limit=limit)
