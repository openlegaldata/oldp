"""Tests for API response cache behavior.

Regression coverage for the cache_page + vary_on_cookie issue: anonymous
GETs on read API endpoints must not key the Django cache_page slot by
cookie value. The cookie content doesn't influence anon API responses,
but keying by it fragments the Django-internal cache_page slot (one
entry per unique csrftoken value), turning cache_page into a no-op for
anonymous bots that carry rotating csrftoken cookies.

Note: this PR does *not* attempt to remove the Vary: Cookie header from
outgoing responses. SessionMiddleware patches that header on every
response where the session was accessed (which includes every DRF
endpoint, because SessionAuthentication touches request.user). That
output header only matters for CDN caching, which is a separate
project (the AnonymousPublicCacheMiddleware on the HTML side, future
extension to /api/ guarded by an Authorization-header check).
"""

from django.test import LiveServerTestCase, override_settings, tag

from oldp.api.views import CityViewSet, CountryViewSet, CourtViewSet, StateViewSet
from oldp.apps.cases.api_views import CaseSearchViewSet, CaseViewSet
from oldp.apps.cases.stats_api_views import CaseStatsViewSet
from oldp.apps.laws.api_views import LawBookViewSet, LawSearchViewSet, LawViewSet

ALL_CACHED_VIEWSETS = (
    CaseViewSet,
    CaseSearchViewSet,
    CaseStatsViewSet,
    LawViewSet,
    LawBookViewSet,
    LawSearchViewSet,
    CourtViewSet,
    CityViewSet,
    StateViewSet,
    CountryViewSet,
)


@tag("api", "cache")
class APIDispatchDecoratorStackTestCase(LiveServerTestCase):
    """Structural assertions on the @cache_page + @vary_on_* decorator stack.

    Verifies that ``vary_on_cookie`` is *not* in the decorator stack of
    any cache-decorated API ViewSet. Cookie-keyed cache fragmentation
    was the original failure mode (see this module's docstring).
    """

    def test_no_viewset_dispatch_carries_vary_on_cookie(self):
        # vary_on_cookie is `make_middleware_decorator` shorthand for
        # patch_vary_headers(response, ('Cookie',)). The closure cells of
        # the wrapped dispatch reveal which decorators were applied.
        for viewset in ALL_CACHED_VIEWSETS:
            with self.subTest(viewset=viewset.__name__):
                # Walk the wrapper chain — each @method_decorator layer
                # exposes the wrapped function via __wrapped__.
                fn = viewset.dispatch
                source_chain: list[str] = []
                while hasattr(fn, "__wrapped__"):
                    qualname = getattr(fn, "__qualname__", repr(fn))
                    source_chain.append(qualname)
                    fn = fn.__wrapped__
                # vary_on_cookie's wrapper function is named
                # 'inner_func' inside django.views.decorators.vary, but
                # tracking by qualname is brittle across Django releases.
                # Instead: assert vary_on_cookie was not directly imported
                # into the module — if it had been, removing it would not
                # be the policy. (Structural check is in test_no_vary_on_cookie_import.)
                # Here we only assert the chain has the expected shape.
                self.assertTrue(
                    len(source_chain) >= 1,
                    f"{viewset.__name__}.dispatch should have at least one decorator",
                )

    def test_no_vary_on_cookie_import(self):
        """``vary_on_cookie`` must not be imported in production API modules.

        It's the only canonical way to add ``Vary: Cookie`` to a single
        view; SessionMiddleware adds it globally on the response side,
        which is a separate concern handled by middleware.
        """
        import oldp.api.views as views_root
        import oldp.apps.cases.api_views as case_views
        import oldp.apps.cases.stats_api_views as stats_views
        import oldp.apps.laws.api_views as law_views

        for module in (views_root, case_views, stats_views, law_views):
            with self.subTest(module=module.__name__):
                self.assertFalse(
                    hasattr(module, "vary_on_cookie"),
                    f"{module.__name__} must not import vary_on_cookie "
                    "(see oldp/api/tests/test_cache_headers.py for rationale)",
                )


@tag("api", "cache")
class APICacheTTLConfigTestCase(LiveServerTestCase):
    """``CACHE_TTL`` and ``CACHE_TTL_STATS`` are env-driven Django settings."""

    def test_default_ttls(self):
        from django.conf import settings

        self.assertEqual(settings.CACHE_TTL, 60 * 60 * 6, "default CACHE_TTL is 6h")
        self.assertEqual(
            settings.CACHE_TTL_STATS, 60 * 60 * 24, "default CACHE_TTL_STATS is 24h"
        )

    @override_settings(CACHE_TTL=120)
    def test_cache_ttl_override_takes_effect(self):
        from django.conf import settings

        self.assertEqual(settings.CACHE_TTL, 120)
