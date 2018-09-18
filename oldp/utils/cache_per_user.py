from django.core.cache import cache
from django.template.response import TemplateResponse


def cache_per_user(ttl=None, prefix=None, cache_post=False):
    """
    Based on https://djangosnippets.org/snippets/2524/

    Decorator for page caching based on user authentication with special cache for guests.

    :param ttl:
    :param prefix:
    :param cache_post: If POST-request should be cached as well
    :return:
    """

    def decorator(function):
        def apply_cache(request, *args, **kwargs):
            # Define user
            if not request.user.is_authenticated:
                user = 'anonymous'
            else:
                user = request.user.id

            # Set cache key
            if prefix:
                CACHE_KEY = '%s_%s' % (prefix, user)
            else:
                # Use url path + query parameters as cache key
                CACHE_KEY = 'view_cache_%s_%s' % (request.get_full_path(), user)

            # Check on POST
            if not cache_post and request.method == 'POST':
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
