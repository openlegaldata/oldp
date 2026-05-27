import logging

from django.apps import AppConfig

logger = logging.getLogger(__name__)


# Hard cap on how many results a single ``_fill_cache`` call may skip.
# The default haystack loop is unbounded: if ``read_queryset`` rejects
# every PK in a chunk (e.g. ES doc references a row that's been
# deleted or otherwise filtered out at hydration time), haystack
# silently advances by ITERATOR_LOAD_PER_QUERY and retries — chunk by
# chunk through the entire result set. We saw 247 ES round-trips for
# ``/search/?q=BGB`` before the ``is_latest`` filter + reindex. This
# cap is defense in depth: after the cap is reached we coerce the
# inner ``query.get_results()`` to return empty so ``_fill_cache``
# takes its natural break path. The page is shorter than requested
# but the request returns instead of hanging the worker.
MAX_FILL_SKIPPED = 200  # = 20 chunks at ITERATOR_LOAD_PER_QUERY=10


def _install_fill_cache_cap():
    from haystack.query import SearchQuerySet

    if getattr(SearchQuerySet, "_oldp_fillcap_installed", False):
        return
    orig_post = SearchQuerySet.post_process_results

    def capped_post(self, results):
        # ``post_process_results`` is the only hook haystack calls per
        # chunk that knows ``len(results)``; track skips here and trip
        # the breaker by returning an empty results list once the cap
        # is hit. The outer ``_fill_cache`` loop then sees ``len(...)
        # == 0`` from the *next* ``get_results`` and exits.
        skipped_before = self._ignored_result_count
        out = orig_post(self, results)
        skipped_total = getattr(self, "_oldp_total_skipped", 0)
        skipped_total += self._ignored_result_count - skipped_before
        self._oldp_total_skipped = skipped_total
        if skipped_total >= MAX_FILL_SKIPPED and not getattr(
            self, "_oldp_capped_logged", False
        ):
            logger.warning(
                "haystack hydration skipped %d ES hits — read_queryset "
                "is dropping many indexed PKs (likely ES/DB drift); "
                "capping the chunk loop. Check for stale docs.",
                skipped_total,
            )
            self._oldp_capped_logged = True
            # Coerce subsequent get_results to return [] so the
            # _fill_cache while-loop terminates cleanly. Resetting at
            # the SearchQuery instance (one per SQS) — safe because
            # SearchQuerySets are not reused across requests.
            _orig_get_results = self.query.get_results

            def _empty_get_results(*args, **kwargs):
                return []

            self.query.get_results = _empty_get_results
        return out

    SearchQuerySet.post_process_results = capped_post
    SearchQuerySet._oldp_fillcap_installed = True


class SearchConfig(AppConfig):
    name = "oldp.apps.search"

    def ready(self):
        _install_fill_cache_cap()
