from rest_framework.throttling import SimpleRateThrottle

from oldp.apps.accounts.models import APIToken


class TokenUserRateThrottle(SimpleRateThrottle):
    """Rate throttle for authenticated users with per-token override support.

    Uses the ``user`` scope from ``DEFAULT_THROTTLE_RATES`` as the default
    rate.  If the request was authenticated with an ``APIToken`` that has a
    non-null ``rate_limit``, that value (requests/hour) overrides the default.

    The cache key is per **user ID** so that a user's total requests are
    counted across all their tokens.

    Anonymous requests return ``None`` from ``get_cache_key`` and are therefore
    skipped (``AnonRateThrottle`` handles those separately).
    """

    scope = "user"

    def __init__(self):
        # Intentionally skip SimpleRateThrottle.__init__ which calls
        # get_rate() before we have a request.  Rate parsing is deferred to
        # allow_request() where we know the request context.
        pass

    def allow_request(self, request, view):
        """Check if the request should be throttled.

        Resolves the applicable rate (per-token override or default) and then
        delegates to the parent implementation.
        """
        if not request.user or not request.user.is_authenticated:
            return True

        # Determine the rate string
        token = request.auth
        if isinstance(token, APIToken) and token.get_rate_limit() is not None:
            rate_string = f"{token.get_rate_limit()}/hour"
        else:
            rate_string = self.get_rate()

        # If no rate is configured at all, allow the request
        if rate_string is None:
            return True

        self.rate = rate_string
        self.num_requests, self.duration = self.parse_rate(self.rate)
        self.key = self.get_cache_key(request, view)

        if self.key is None:
            return True

        self.history = self.cache.get(self.key, [])
        self.now = self.timer()

        # Drop requests outside the current window
        while self.history and self.history[-1] <= self.now - self.duration:
            self.history.pop()

        if len(self.history) >= self.num_requests:
            return self.throttle_failure()
        return self.throttle_success()

    def get_rate(self):
        """Return the default rate from DEFAULT_THROTTLE_RATES['user'].

        Reads the setting at request time so that ``override_settings`` in
        tests and runtime changes are respected (the class-level
        ``THROTTLE_RATES`` attribute is evaluated once at import time).
        """
        from rest_framework.settings import api_settings

        rates = api_settings.DEFAULT_THROTTLE_RATES or {}
        return rates.get(self.scope)

    def get_cache_key(self, request, view):
        """Return a cache key based on the authenticated user's ID.

        Returns ``None`` for anonymous requests so they are not throttled by
        this class.
        """
        if request.user and request.user.is_authenticated:
            return f"throttle_user_{request.user.pk}"
        return None
