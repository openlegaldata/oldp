"""Caller identity and rate-limit budget, shared by ``/api/whoami/`` and MCP.

Both surfaces answer the same question for the caller: am I signed in, which
rate-limit tier applies, how much of the budget is left, and how can I get a
larger one. The budget is read from the same throttle cache buckets that
enforce it, so the numbers match what the throttles will do next.

Reading the budget never records a request. The request asking the question
has already been counted by the view's throttles when this runs.
"""

import math

from django.conf import settings
from django.urls import NoReverseMatch, reverse
from rest_framework.settings import api_settings
from rest_framework.throttling import SimpleRateThrottle

from oldp.api.throttling import TokenUserRateThrottle
from oldp.apps.accounts.models import APIToken

_PERIOD_NAMES = {"s": "second", "m": "minute", "h": "hour", "d": "day"}


def describe_caller(request, throttles) -> dict:
    """Return who is calling and the rate-limit budget that applies to them.

    Args:
        request: The DRF request (``user`` and ``auth`` already resolved).
        throttles: Throttle instances that guard the surface being asked
            about, e.g. ``view.get_throttles()``. The first one that applies
            to this request determines the reported budget.

    Returns:
        A dict with ``authenticated``, ``user`` (``username`` and
        ``profile_complete``, or ``None``), ``auth_method``, ``rate_limit``
        (see :func:`rate_limit_status`) and ``upgrade`` (how to get a larger
        budget, or ``None``).
    """
    user = getattr(request, "user", None)
    authenticated = bool(user and user.is_authenticated)
    profile = getattr(user, "profile", None) if authenticated else None

    status = rate_limit_status(request, throttles)
    return {
        "authenticated": authenticated,
        "user": (
            {
                "username": user.get_username(),
                "profile_complete": bool(profile and profile.is_profile_complete),
            }
            if authenticated
            else None
        ),
        "auth_method": _auth_method(request) if authenticated else None,
        "rate_limit": status,
        "upgrade": _upgrade(status),
    }


def rate_limit_status(request, throttles) -> dict | None:
    """Return the budget of the first throttle that applies to ``request``.

    The result has ``tier`` (``anonymous``, ``registered``, ``enriched`` or
    ``custom``), ``bucket`` (``ip``, ``shared`` or ``user``), ``limit`` and
    ``window_seconds`` (``None`` when unlimited), ``used``, ``remaining``,
    and ``retry_after_seconds`` (only set once the budget is used up).
    Returns ``None`` when no throttle applies.
    """
    if not hasattr(request, "META"):
        return None
    for throttle in throttles:
        if isinstance(throttle, TokenUserRateThrottle):
            if not (request.user and request.user.is_authenticated):
                continue
            rate, tier = throttle.resolve_rate(request)
            key = throttle.get_cache_key(request, None)
            bucket = "user"
        elif isinstance(throttle, SimpleRateThrottle):
            key = throttle.get_cache_key(request, None)
            if key is None:
                continue
            rate, tier = throttle.rate, "anonymous"
            describe_bucket = getattr(throttle, "describe_bucket", None)
            bucket = describe_bucket(key) if describe_bucket else "ip"
        else:
            continue
        return _budget(throttle, key, rate, tier, bucket)
    return None


def _budget(throttle, key, rate, tier, bucket) -> dict:
    """Count the requests in ``key``'s current window against ``rate``."""
    status = {
        "tier": tier,
        "bucket": bucket,
        "limit": None,
        "window_seconds": None,
        "used": None,
        "remaining": None,
        "retry_after_seconds": None,
    }
    if rate is None or key is None:
        return status

    limit, duration = throttle.parse_rate(rate)
    now = throttle.timer()
    # Histories are newest first; the last in-window entry expires next.
    window = [ts for ts in throttle.cache.get(key, []) if ts > now - duration]
    remaining = max(0, limit - len(window))
    status.update(
        limit=limit,
        window_seconds=duration,
        used=len(window),
        remaining=remaining,
    )
    if remaining == 0 and window:
        status["retry_after_seconds"] = max(0, math.ceil(window[-1] + duration - now))
    return status


def _auth_method(request) -> str:
    """Name the mechanism that authenticated ``request``."""
    from oauth2_provider.models import get_access_token_model
    from rest_framework.authtoken.models import Token

    auth = getattr(request, "auth", None)
    if isinstance(auth, APIToken):
        return "api_token"
    if isinstance(auth, get_access_token_model()):
        return "oauth"
    if isinstance(auth, Token):
        return "legacy_token"
    return "session"


def _upgrade(status: dict | None) -> dict | None:
    """How the caller can raise their budget, or ``None`` if they can't."""
    if status is None:
        return None
    rates = api_settings.DEFAULT_THROTTLE_RATES or {}
    if status["tier"] == "anonymous" and rates.get("user"):
        shared = (
            "Anonymous requests from this client share one budget with all "
            "other anonymous users of the same connector. "
            if status["bucket"] == "shared"
            else ""
        )
        return {
            "action": "sign_up",
            "url": _site_url("account_signup"),
            "limit": _describe_rate(rates["user"]),
            "message": (
                f"You are not signed in. {shared}Create a free account and "
                "connect with OAuth (MCP) or send an API token (REST API) to "
                f"get your own budget of {_describe_rate(rates['user'])}."
            ),
        }
    if status["tier"] == "registered" and rates.get("enriched"):
        return {
            "action": "complete_profile",
            "url": _site_url("account_profile"),
            "limit": _describe_rate(rates["enriched"]),
            "message": (
                "Complete your profile (role and use case) to raise your "
                f"limit to {_describe_rate(rates['enriched'])}."
            ),
        }
    return None


def _describe_rate(rate: str) -> str:
    """Render a DRF rate such as ``"5000/hour"`` as ``"5000 requests/hour"``."""
    num, period = rate.split("/")
    return f"{num} requests/{_PERIOD_NAMES.get(period[:1], period)}"


def _site_url(url_name: str) -> str | None:
    """Absolute URL of a named route on the public site."""
    try:
        path = reverse(url_name)
    except NoReverseMatch:
        return None
    site = getattr(settings, "SITE_URL", "") or ""
    return f"{site.rstrip('/')}{path}"
