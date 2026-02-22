from functools import wraps

from django.core.cache import cache
from django.template.response import TemplateResponse


def _response_has_vary_cookie(response):
    vary_header = response.get("Vary", "")
    if not vary_header:
        return False
    return "cookie" in {item.strip().lower() for item in vary_header.split(",")}


def cache_per_role(ttl=None, cache_post=False):
    """Cache view response per user role (anonymous, authenticated, staff).

    Unlike cache_per_user which creates one entry per user ID, this creates
    at most 3 entries per URL path — suitable for views with no per-individual-user content.
    """

    def decorator(function):
        @wraps(function)
        def apply_cache(request, *args, **kwargs):
            user = getattr(request, "user", None)
            if not user or not user.is_authenticated:
                role = "anon"
            elif user.is_staff:
                role = "staff"
            else:
                role = "auth"

            try:
                host = request.get_host()
            except Exception:
                host = request.META.get("HTTP_HOST", "unknown")
            lang = getattr(request, "LANGUAGE_CODE", None) or "default"
            method = "GET" if request.method == "HEAD" else request.method
            CACHE_KEY = "view_cache_%s_%s_%s_%s_%s" % (
                host,
                lang,
                method,
                request.get_full_path(),
                role,
            )

            if not cache_post and request.method == "POST":
                can_cache = False
            else:
                can_cache = True

            if can_cache:
                response = cache.get(CACHE_KEY, None)
            else:
                response = None

            if not response:
                response = function(request, *args, **kwargs)

                if isinstance(response, TemplateResponse):
                    response = response.render()

                has_set_cookie = response.has_header("Set-Cookie") or bool(
                    getattr(response, "cookies", None)
                )
                response_is_cacheable = (
                    response.status_code == 200
                    and not getattr(response, "streaming", False)
                    and not has_set_cookie
                    and not _response_has_vary_cookie(response)
                )
                if can_cache and response_is_cacheable:
                    cache.set(CACHE_KEY, response, ttl)
            return response

        return apply_cache

    return decorator


def cache_per_user(ttl=None, prefix=None, cache_post=False):
    """Based on https://djangosnippets.org/snippets/2524/

    Decorator for page caching based on user authentication with special cache for guests.

    :param ttl:
    :param prefix:
    :param cache_post: If POST-request should be cached as well
    :return:
    """

    def decorator(function):
        @wraps(function)
        def apply_cache(request, *args, **kwargs):
            # Define user
            if not request.user.is_authenticated:
                user = "anonymous"
            else:
                user = request.user.id

            # Set cache key
            if prefix:
                CACHE_KEY = "%s_%s" % (prefix, user)
            else:
                # Use url path + query parameters as cache key
                CACHE_KEY = "view_cache_%s_%s" % (request.get_full_path(), user)

            # Check on POST
            if not cache_post and request.method == "POST":
                can_cache = False
            else:
                can_cache = True

            if can_cache:
                response = cache.get(CACHE_KEY, None)
            else:
                response = None

            if not response:
                response = function(request, *args, **kwargs)

                # Render response when decorator is used on ListViews
                if isinstance(response, TemplateResponse):
                    response = response.render()

                if can_cache:
                    cache.set(CACHE_KEY, response, ttl)
            return response

        return apply_cache

    return decorator
