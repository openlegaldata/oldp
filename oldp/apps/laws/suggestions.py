"""Fuzzy ``did_you_mean`` suggestions for law-book codes.

When a caller (REST, MCP, or an LLM agent) asks for a law book that does
not exist — a typo like ``BGBB``, a guess like ``DSGVOO``, or a wrong
casing — a bare "not found" is a dead end. These helpers return the
closest *existing* book codes so the error can carry a recovery hint
(see B10 in ``search-improvements.md``).

The matching logic is split out as a pure function so it can be unit
tested without touching the database.
"""

# closest_codes moved to oldp.utils.suggestions (shared with courts);
# re-exported here for the existing import path / tests.
from oldp.utils.suggestions import closest_codes

__all__ = ["closest_codes", "suggest_book_codes"]


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
