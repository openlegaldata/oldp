"""Response caching for the read API.

The cached viewsets deliberately do **not** carry ``vary_on_cookie``: keying
the ``cache_page`` slot by cookie value fragments it into one entry per
distinct ``csrftoken``, which turns the cache into a no-op against anonymous
bots that rotate cookies. See ``oldp.api.tests.test_cache_headers``.

That alone is unsafe, though. ``cache_page`` stores whatever the view
returned under a key derived from the request path plus the headers named in
``vary_on_headers`` — and ``Authorization`` is not sent by a session-logged-in
user. A staff member browsing ``/api/cases/`` over a session cookie therefore
wrote their *privileged* response (pending rows, ``review_status`` exposed)
into the slot that anonymous requests read from, for the whole ``CACHE_TTL``.

The outgoing ``Vary: Cookie`` header does not prevent this. It is appended by
``SessionMiddleware`` during the response phase, after the ``cache_page``
decorator has already computed its key and stored the entry, so the header
only influences downstream (CDN) caches, never the Django-internal slot.

The fix is to keep the shared slot strictly anonymous: requests carrying any
credential bypass ``cache_page`` in both directions -- they are neither served
from it nor written into it. Anonymous traffic keeps the unfragmented fast
path the cookie-keying change was introduced to protect.
"""

import functools

from django.views.decorators.cache import cache_page


def request_is_authenticated(request) -> bool:
    """True when ``request`` carries any credential.

    Two independent mechanisms reach these viewsets and they resolve at
    different times:

    * **Session** — ``AuthenticationMiddleware`` runs before the view, so
      ``request.user`` is already resolvable here.
    * **Token** — DRF authenticates inside ``initialize_request``, i.e. after
      this decorator has run, so ``request.user`` is still anonymous at this
      point. Fall back to the presence of the ``Authorization`` header.

    Erring towards "authenticated" is the safe direction: the cost is a cache
    miss, whereas the opposite error is a privileged response in a shared slot.
    """
    user = getattr(request, "user", None)
    if user is not None and user.is_authenticated:
        return True
    return bool(request.META.get("HTTP_AUTHORIZATION"))


def cache_page_for_anonymous(timeout):
    """``cache_page(timeout)`` restricted to unauthenticated requests.

    Authenticated requests execute the view directly, so a per-user response
    can neither be served from nor written to the shared anonymous entry.
    """
    cache_page_decorator = cache_page(timeout)

    def decorator(view_func):
        cached_view = cache_page_decorator(view_func)

        @functools.wraps(view_func)
        def _wrapped(request, *args, **kwargs):
            if request_is_authenticated(request):
                return view_func(request, *args, **kwargs)
            return cached_view(request, *args, **kwargs)

        return _wrapped

    return decorator
