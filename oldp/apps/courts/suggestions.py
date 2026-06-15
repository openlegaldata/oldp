"""Fuzzy ``did_you_mean`` suggestions for court identifiers.

When ``get_court`` is asked for a court code/slug that does not exist (a
typo or a guessed ECLI code), return the closest existing identifiers so
the error can carry a recovery hint. Mirrors ``laws.suggestions`` and
shares the pure matcher in ``oldp.utils.suggestions``.
"""

from oldp.utils.suggestions import closest_codes


def suggest_court_codes(code, limit=5):
    """Suggest existing court ECLI codes close to ``code`` (DB-backed)."""
    from oldp.apps.courts.models import Court

    candidates = (
        Court.objects.filter(review_status="accepted")
        .exclude(code="")
        .values_list("code", flat=True)
        .distinct()
    )
    return closest_codes(code, candidates, limit=limit)


def suggest_court_slugs(slug, limit=5):
    """Suggest existing court slugs close to ``slug`` (DB-backed)."""
    from oldp.apps.courts.models import Court

    candidates = (
        Court.objects.filter(review_status="accepted")
        .exclude(slug="")
        .values_list("slug", flat=True)
        .distinct()
    )
    return closest_codes(slug, candidates, limit=limit)
