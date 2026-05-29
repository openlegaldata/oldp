"""Cache helpers for case detail view.

The case detail view (`case_view`) caches three artefacts under slug-only
keys. To keep `review_status` filtering honest, the cache must:

- skip writes for non-accepted cases (so a staff/creator preview cannot
  poison the cache for anonymous visitors), and
- be invalidated whenever a case's `review_status` changes (so an
  accepted-then-demoted case stops being served).
"""

from django.core.cache import cache

CASE_DATA_KEY = "case_data_v2_%s"
CASE_PUBLIC_MARKERS_KEY = "case_public_markers_%s"
CASE_CONTENT_ANON_KEY = "case_content_anon_%s"


def invalidate_case_cache(case_slug: str) -> None:
    """Drop every slug-keyed cache entry for ``case_slug``."""
    cache.delete_many(
        [
            CASE_DATA_KEY % case_slug,
            CASE_PUBLIC_MARKERS_KEY % case_slug,
            CASE_CONTENT_ANON_KEY % case_slug,
        ]
    )
