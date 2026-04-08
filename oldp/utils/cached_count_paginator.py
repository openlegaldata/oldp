import hashlib

from django.conf import settings
from django.core.cache import cache
from django.core.paginator import Paginator
from django.utils.functional import cached_property


class CachedCountPaginator(Paginator):
    """Paginator that caches the COUNT(*) query result.

    The count is cached per queryset SQL fingerprint for CACHE_TTL seconds.
    Falls back to the standard count() if caching fails.
    """

    CACHE_KEY_PREFIX = "paginator_count"

    def _get_cache_key(self):
        """Generate a cache key from the queryset's SQL."""
        sql = str(self.object_list.query)
        sql_hash = hashlib.md5(sql.encode()).hexdigest()
        return f"{self.CACHE_KEY_PREFIX}:{sql_hash}"

    @cached_property
    def count(self):
        """Return the total number of objects, using cache for QuerySets."""
        if not hasattr(self.object_list, "query"):
            return len(self.object_list)
        try:
            cache_key = self._get_cache_key()
            cached_count = cache.get(cache_key)
            if cached_count is not None:
                return cached_count
            real_count = self.object_list.count()
            cache.set(cache_key, real_count, settings.CACHE_TTL)
            return real_count
        except Exception:
            return self.object_list.count()
