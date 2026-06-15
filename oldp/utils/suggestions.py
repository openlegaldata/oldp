"""Generic fuzzy ``did_you_mean`` matching for short codes/identifiers.

Pure (no DB) so it can be unit tested in isolation and reused across apps
(law-book codes, court codes, …). DB-backed wrappers live in each app
(``laws.suggestions``, ``courts.suggestions``).
"""

import difflib


def closest_codes(code, candidates, limit=5):
    """Return up to ``limit`` codes from ``candidates`` closest to ``code``.

    Combines two cheap signals, both case-insensitive:

    1. **Prefix matches** — an existing code that starts with the query, or
       a query that starts with an existing code (catches ``DSGVOO`` →
       ``DSGVO`` and ``BGB`` → ``BGBEG``). Ranked shortest-first.
    2. **Edit-distance matches** via :func:`difflib.get_close_matches`
       (catches transpositions / single-char typos like ``StPOO``).

    Prefix matches come first (a strong signal for code lookups), then
    edit-distance matches, de-duplicated, preserving the candidate's
    original casing. An exact (case-insensitive) hit is never returned —
    that is not a "did you mean".

    Args:
        code: The (wrong) code the caller asked for.
        candidates: Iterable of existing codes.
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
