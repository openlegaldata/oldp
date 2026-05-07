"""MCP endpoint view with OAuth2 authentication and MCP-specific throttling."""

import fnmatch
from urllib.parse import urlparse

from django.conf import settings
from django.http import HttpResponseNotAllowed
from mcp_server.views import MCPServerStreamableHttpView
from oauth2_provider.contrib.rest_framework import OAuth2Authentication
from rest_framework.authentication import (
    SessionAuthentication,
    get_authorization_header,
)
from rest_framework.exceptions import AuthenticationFailed, PermissionDenied
from rest_framework.permissions import AllowAny

from oldp.apps.accounts.authentication import CombinedTokenAuthentication
from oldp.apps.mcp.throttles import MCPAnonThrottle, MCPUserThrottle


def _origin_from_url(url: str) -> str:
    """Return the scheme+host origin from a URL or an empty string."""
    parsed = urlparse((url or "").strip())
    if not parsed.scheme or not parsed.netloc:
        return ""
    return f"{parsed.scheme}://{parsed.netloc}".lower()


def _origin_matches(pattern: str, origin: str) -> bool:
    """Return whether an origin matches an exact or wildcard trusted pattern."""
    pattern = (pattern or "").rstrip("/").lower()
    origin = (origin or "").rstrip("/").lower()
    if not pattern or not origin:
        return False
    if "*" in pattern:
        return fnmatch.fnmatchcase(origin, pattern)
    return origin == pattern


class StrictOAuth2Authentication(OAuth2Authentication):
    """OAuth2 auth that rejects invalid Bearer headers instead of ignoring them."""

    def authenticate(self, request):
        result = super().authenticate(request)
        if result is not None:
            return result

        auth = get_authorization_header(request).split()
        if auth and auth[0].lower() == b"bearer":
            raise AuthenticationFailed("Invalid bearer token.")
        return None


class OLDPMCPView(MCPServerStreamableHttpView):
    """MCP Streamable HTTP endpoint for OLDP.

    Supports anonymous access (no authentication required) with rate limiting.
    Authenticated users (via OAuth2 or API token) get higher rate limits.
    """

    authentication_classes = [
        StrictOAuth2Authentication,
        CombinedTokenAuthentication,
        SessionAuthentication,
    ]
    permission_classes = [AllowAny]
    throttle_classes = [MCPAnonThrottle, MCPUserThrottle]
    http_method_names = ["post", "delete", "options"]

    def dispatch(self, request, *args, **kwargs):
        """Return method errors before DRF content negotiation runs."""
        if request.method == "GET":
            return HttpResponseNotAllowed(["POST", "DELETE"])
        return super().dispatch(request, *args, **kwargs)

    def initial(self, request, *args, **kwargs):
        """Reject cross-origin browser requests before MCP processing."""
        self._validate_origin(request)
        return super().initial(request, *args, **kwargs)

    def _validate_origin(self, request):
        """Validate the Origin header required by MCP Streamable HTTP."""
        origin = request.headers.get("Origin")
        if not origin:
            return

        normalized_origin = _origin_from_url(origin)
        allowed_origins = {
            _origin_from_url(getattr(settings, "SITE_URL", "")),
        }
        try:
            allowed_origins.add(_origin_from_url(request.build_absolute_uri("/")))
        except Exception:
            pass

        allowed_origins.update(
            _origin_from_url(origin)
            for origin in getattr(settings, "CSRF_TRUSTED_ORIGINS", [])
        )
        allowed_origins.discard("")

        if any(
            _origin_matches(pattern, normalized_origin) for pattern in allowed_origins
        ):
            return

        raise PermissionDenied("Invalid Origin for MCP endpoint.")
