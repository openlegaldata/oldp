import hashlib
import logging

from django.conf import settings
from django.core.cache import cache
from django.core.exceptions import EmptyResultSet
from django.core.paginator import Paginator
from django.utils.functional import cached_property

logger = logging.getLogger(__name__)

CACHE_KEY_PREFIX = "paginator_count"


def _count_cache_key(queryset) -> str | None:
    """Cache key derived from the queryset's SQL fingerprint.

    Returns ``None`` when the queryset is provably empty and therefore has no
    SQL to fingerprint. Django raises ``EmptyResultSet`` from the compiler when
    a lookup can never match -- most commonly an ``IN ()`` from an empty id
    list, which the citing-case and citing-law helpers produce whenever a
    section has no citations. That is control flow inside Django, not a
    failure, so it must not reach the caller's error path.
    """
    try:
        sql = str(queryset.query)
    except EmptyResultSet:
        return None
    sql_hash = hashlib.md5(sql.encode()).hexdigest()
    return f"{CACHE_KEY_PREFIX}:{sql_hash}"


def cached_queryset_count(queryset) -> int:
    """``queryset.count()``, memoised in the cache for ``CACHE_TTL`` seconds.

    Pagination issues a ``COUNT(*)`` before every page. On large tables that
    count dominates the request: the prod slow log had a bare
    ``SELECT COUNT(*) FROM references_reference`` examining **18.6 million
    rows** to return one number, at ~3.3s a call.

    Keyed on the queryset SQL, so filtered and unfiltered variants cache
    independently. The trade-off is that a reported total can lag by up to
    ``CACHE_TTL`` — acceptable for list pagination, and the same trade-off
    ``CachedCountPaginator`` already makes for the page-number endpoints.

    Falls back to an uncached ``count()`` if anything goes wrong, so a cache
    outage degrades to today's behaviour rather than erroring.

    A provably-empty queryset is not cached: there is no SQL to key on, and
    ``count()`` short-circuits to 0 without touching the database.
    """
    if not hasattr(queryset, "query"):
        return len(queryset)
    cache_key = _count_cache_key(queryset)
    if cache_key is None:
        return queryset.count()
    try:
        cached_count = cache.get(cache_key)
        if cached_count is not None:
            return cached_count
        real_count = queryset.count()
        cache.set(cache_key, real_count, settings.CACHE_TTL)
        return real_count
    except Exception:
        logger.warning("Cached count failed; falling back to COUNT(*)", exc_info=True)
        return queryset.count()


class CachedCountPaginator(Paginator):
    """Paginator that caches the COUNT(*) query result.

    The count is cached per queryset SQL fingerprint for CACHE_TTL seconds.
    Falls back to the standard count() if caching fails.
    """

    CACHE_KEY_PREFIX = CACHE_KEY_PREFIX

    def _get_cache_key(self):
        """Generate a cache key from the queryset's SQL."""
        return _count_cache_key(self.object_list)

    @cached_property
    def count(self):
        """Return the total number of objects, using cache for QuerySets."""
        return cached_queryset_count(self.object_list)
