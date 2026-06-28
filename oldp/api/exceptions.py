from django.conf import settings
from django.urls import reverse
from rest_framework.exceptions import APIException, Throttled
from rest_framework.views import exception_handler

from oldp.apps.accounts.models import APIToken


def _site_url(path):
    """Absolute URL for a site-relative path, based on SITE_URL."""
    base = getattr(settings, "SITE_URL", "") or ""
    return base.rstrip("/") + path


def _is_mcp_view(view):
    """True when the throttled view belongs to the MCP app."""
    return view is not None and type(view).__module__.startswith("oldp.apps.mcp")


def _throttle_upgrade(request, view):
    """Build the upgrade call-to-action attached to a 429 response.

    A 429 is the moment a client feels the free-tier limit, so we tell them how
    to get more. Copy is deliberately English (developer/API audience) and never
    quotes a numeric limit. It is tailored by surface (REST API vs MCP) and by
    who hit the wall (anonymous / free authenticated / a paying token).
    """
    contact_url = _site_url(reverse("contact:form"))
    docs_url = getattr(settings, "SITE_API_DOCS_URL", "")
    is_mcp = _is_mcp_view(view)

    user = getattr(request, "user", None)
    authenticated = bool(user and user.is_authenticated)

    # A token carrying an explicit rate_limit override is a paying customer.
    token = getattr(request, "auth", None)
    has_custom_limit = (
        isinstance(token, APIToken) and token.get_rate_limit() is not None
    )

    if not authenticated:
        if is_mcp:
            message = (
                "You've hit the rate limit for anonymous MCP access. Sign in "
                "with your Open Legal Data account for higher limits, or contact "
                "us for production access."
            )
        else:
            message = (
                "You've hit the anonymous API rate limit. Register a free Open "
                "Legal Data account for higher limits, or contact us for "
                "production access."
            )
        upgrade = {
            "message": message,
            "register_url": _site_url(reverse("account_signup")),
            "contact_url": contact_url,
        }
    elif has_custom_limit:
        upgrade = {
            "message": (
                "You've reached the rate limit on your API token. Contact us to "
                "raise your contracted limit."
            ),
            "contact_url": contact_url,
        }
    elif is_mcp:
        upgrade = {
            "message": (
                "You've hit your MCP rate limit. Contact us for higher or "
                "premium MCP access."
            ),
            "contact_url": contact_url,
        }
    else:
        upgrade = {
            "message": (
                "You've hit your API rate limit. Need higher limits for "
                "production use? Contact us for production access."
            ),
            "contact_url": contact_url,
        }

    if docs_url:
        upgrade["docs_url"] = docs_url
    return upgrade


def full_details_exception_handler(exc, context):
    """This overrides the default exception handler to
    include the human-readable message AND the error code
    so that clients can respond programmatically.

    On a 429 (rate limited) it additionally attaches an ``upgrade`` call-to-
    action and ``retry_after`` so clients learn how to get higher limits — the
    free-tier limit is the natural conversion trigger.
    """
    if isinstance(exc, APIException):
        exc.detail = exc.get_full_details()

    response = exception_handler(exc, context)

    if (
        isinstance(exc, Throttled)
        and response is not None
        and isinstance(response.data, dict)
    ):
        request = context.get("request")
        if request is not None:
            response.data["upgrade"] = _throttle_upgrade(request, context.get("view"))
        if exc.wait is not None:
            response.data["retry_after"] = int(exc.wait)

    return response
