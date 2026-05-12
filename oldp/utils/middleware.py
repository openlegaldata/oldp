"""Middleware utilities for OLDP."""

from __future__ import annotations

from typing import Callable

from django.conf import settings
from django.http import HttpRequest, HttpResponseBase

DEFAULT_ANON_CACHE_PATH_PREFIXES: tuple[str, ...] = (
    "/case/",
    "/law/",
    "/court/",
    "/pages/",
    "/search/",
)
DEFAULT_ANON_CACHE_PATHS_EXACT: tuple[str, ...] = ("/",)
DEFAULT_ANON_CACHE_S_MAXAGE: int = 600  # 10 minutes at the CDN edge
DEFAULT_ANON_CACHE_MAX_AGE: int = 60  # 1 minute in the browser


class AnonymousPublicCacheMiddleware:
    """Make anonymous GETs on public pages CDN-cacheable.

    Without this, ``SessionMiddleware``/``AuthenticationMiddleware`` tag
    every response with ``Vary: Cookie`` whenever the session is touched
    (which happens on virtually every page because the navbar tests
    ``user.is_authenticated``). A CDN respecting ``Vary: Cookie`` keys
    each unique cookie value separately, and anonymous bots typically
    carry several cookies (``csrftoken``, analytics, etc.), so cache
    key fan-out collapses the effective hit rate.

    For anonymous GET/HEAD on cacheable paths this middleware:

    * Replaces ``Vary: Cookie`` with ``Vary: Accept-Encoding`` so all
      anonymous responses share one cache key per URL.
    * Clears any ``Set-Cookie`` headers (the cacheable pages render only
      GET forms — no ``{% csrf_token %}`` — so no cookies need to flow
      to anonymous visitors).
    * Sets ``Cache-Control: public`` with finite ``s-maxage`` so the
      CDN treats the response as cacheable.

    Logged-in users (carrying ``sessionid``) are untouched: they keep
    their ``Vary: Cookie`` responses, and the CDN bypasses cache for
    them via its own rule. This middleware is therefore safe to enable
    by default in production.

    Configurable Django settings (all optional):

    * ``ANON_CACHE_ENABLED`` (bool, default ``True``): master switch.
      Set to ``False`` to neutralize the middleware without removing
      it from ``MIDDLEWARE``.
    * ``ANON_CACHE_PATH_PREFIXES`` (iterable of str): URL prefixes that
      should become public-cacheable for anonymous visitors. Default:
      ``("/case/", "/law/", "/court/", "/pages/", "/search/")``.
    * ``ANON_CACHE_PATHS_EXACT`` (iterable of str): exact paths to
      cover. Default: ``("/",)`` so the homepage is included.
    * ``ANON_CACHE_S_MAXAGE`` (int, seconds): CDN edge TTL. Default 600.
    * ``ANON_CACHE_MAX_AGE`` (int, seconds): browser TTL. Default 60.
    """

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponseBase]):
        self.get_response = get_response
        self.enabled: bool = getattr(settings, "ANON_CACHE_ENABLED", True)
        self.prefixes: tuple[str, ...] = tuple(
            getattr(
                settings, "ANON_CACHE_PATH_PREFIXES", DEFAULT_ANON_CACHE_PATH_PREFIXES
            )
        )
        self.exact: frozenset[str] = frozenset(
            getattr(settings, "ANON_CACHE_PATHS_EXACT", DEFAULT_ANON_CACHE_PATHS_EXACT)
        )
        self.s_maxage: int = int(
            getattr(settings, "ANON_CACHE_S_MAXAGE", DEFAULT_ANON_CACHE_S_MAXAGE)
        )
        self.max_age: int = int(
            getattr(settings, "ANON_CACHE_MAX_AGE", DEFAULT_ANON_CACHE_MAX_AGE)
        )

    def __call__(self, request: HttpRequest) -> HttpResponseBase:
        response = self.get_response(request)
        if self.enabled and self._applies(request, response):
            self._make_public_cacheable(response)
        return response

    def _applies(self, request: HttpRequest, response: HttpResponseBase) -> bool:
        if request.method not in ("GET", "HEAD"):
            return False
        if response.status_code != 200:
            return False
        user = getattr(request, "user", None)
        if user is not None and not getattr(user, "is_anonymous", True):
            return False
        path = request.path or ""
        if path in self.exact:
            return True
        return any(path.startswith(p) for p in self.prefixes)

    def _make_public_cacheable(self, response: HttpResponseBase) -> None:
        response.headers["Vary"] = "Accept-Encoding"
        response.cookies.clear()
        response.headers["Cache-Control"] = (
            f"public, s-maxage={self.s_maxage}, max-age={self.max_age}"
        )
