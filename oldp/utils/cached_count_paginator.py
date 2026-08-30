import hashlib
import logging

from django.conf import settings
from django.core.cache import cache
from django.core.paginator import Paginator
from django.utils.functional import cached_property

logger = logging.getLogger(__name__)

CACHE_KEY_PREFIX = "paginator_count"


def _count_cache_key(queryset) -> str:
    """Cache key derived from the queryset's SQL fingerprint."""
    sql = str(queryset.query)
    sql_hash = hashlib.md5(sql.encode()).hexdigest()
    return f"{CACHE_KEY_PREFIX}:{sql_hash}"


def cached_queryset_count(queryset) -> int:
    """``queryset.count()``, memoised in the cache for ``CACHE_TTL`` seconds.

    Pagination issues a ``COUNT(*)`` before every page. On large tables that
    count dominates the request: the prod slow log had a bare
    ``SELECT COUNT(*) FROM references_reference`` examining **18.6 million
    rows** to return one number, at ~3.3s a call (internal-tools#5).

    Keyed on the queryset SQL, so filtered and unfiltered variants cache
    independently. The trade-off is that a reported total can lag by up to
    ``CACHE_TTL`` — acceptable for list pagination, and the same trade-off
    ``CachedCountPaginator`` already makes for the page-number endpoints.

    Falls back to an uncached ``count()`` if anything goes wrong, so a cache
    outage degrades to today's behaviour rather than erroring.
    """
    if not hasattr(queryset, "query"):
        return len(queryset)
    try:
        cache_key = _count_cache_key(queryset)
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
