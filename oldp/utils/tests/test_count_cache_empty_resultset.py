"""A provably-empty queryset must not take the cache error path.

``_count_cache_key`` fingerprints ``str(queryset.query)``. Django's compiler
raises ``EmptyResultSet`` from that call when a lookup can never match -- most
commonly ``IN ()`` from an empty id list, which the citing-case/citing-law
helpers produce for any section with no citations.

That is control flow inside Django, not an error. Before the fix it escaped
into the generic ``except Exception`` handler, logging a full traceback at
WARNING for every such request -- ~600 an hour in production, all for requests
that were served correctly as 200.
"""

import logging

from django.core.exceptions import EmptyResultSet
from django.test import TestCase, override_settings

from oldp.apps.cases.models import Case
from oldp.utils.cached_count_paginator import (
    CachedCountPaginator,
    _count_cache_key,
    cached_queryset_count,
)

LOCMEM = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "count-cache-empty",
    }
}


@override_settings(CACHES=LOCMEM)
class EmptyResultSetCountTestCase(TestCase):
    def setUp(self):
        self.empty = Case.objects.filter(id__in=[])

    def test_str_on_the_query_really_does_raise(self):
        """Guard the premise: without this, the rest of the module is vacuous."""
        with self.assertRaises(EmptyResultSet):
            str(self.empty.query)

    def test_cache_key_is_none_for_empty_queryset(self):
        self.assertIsNone(_count_cache_key(self.empty))

    def test_count_is_zero_and_not_an_error(self):
        self.assertEqual(cached_queryset_count(self.empty), 0)

    def test_no_warning_is_logged(self):
        """The regression itself: this used to emit a traceback at WARNING."""
        with self.assertNoLogs(
            "oldp.utils.cached_count_paginator", level=logging.WARNING
        ):
            cached_queryset_count(self.empty)

    def test_no_database_query_is_issued(self):
        """An impossible WHERE is short-circuited by Django, not sent to the DB."""
        with self.assertNumQueries(0):
            self.assertEqual(cached_queryset_count(self.empty), 0)

    def test_paginator_count_path_is_also_safe(self):
        """``CachedCountPaginator`` shares the helper and must not raise."""
        paginator = CachedCountPaginator(self.empty, 25)
        self.assertEqual(paginator.count, 0)
        self.assertIsNone(paginator._get_cache_key())

    def test_non_empty_queryset_still_caches(self):
        """The fix must not disable caching for ordinary querysets."""
        normal = Case.objects.all()
        key = _count_cache_key(normal)
        self.assertIsNotNone(key)
        self.assertTrue(key.startswith("paginator_count:"))
        self.assertEqual(cached_queryset_count(normal), 0)
        # Second call is served from cache -- no COUNT(*) issued.
        with self.assertNumQueries(0):
            cached_queryset_count(normal)
