"""MCP endpoint view with OAuth2 authentication and MCP-specific throttling."""

import fnmatch
import json
import logging
from urllib.parse import urlparse

from django.conf import settings
from django.http import Http404, HttpResponse, HttpResponseNotAllowed
from django.urls import reverse
from django.views.decorators.http import require_GET
from mcp_server.views import MCPServerStreamableHttpView
from oauth2_provider.contrib.rest_framework import OAuth2Authentication
from rest_framework.authentication import (
    SessionAuthentication,
    get_authorization_header,
)
from rest_framework.exceptions import (
    AuthenticationFailed,
    NotAuthenticated,
    PermissionDenied,
)
from rest_framework.permissions import AllowAny

from oldp.apps.accounts.authentication import CombinedTokenAuthentication
from oldp.apps.mcp.throttles import MCP_THROTTLE_CLASSES

logger = logging.getLogger("oldp.mcp.transport")

#: Tools that only signed-in callers may use. Calling one without credentials
#: is answered with HTTP 401 and an OAuth challenge (see
#: ``OLDPMCPView.check_permissions``), so a client whose connector signs in
#: only "when the server asks" offers the sign-in instead of showing an error.
SIGN_IN_REQUIRED_TOOLS = frozenset({"submit_feedback"})


def _called_tools(body: bytes) -> set[str]:
    """Names of the tools that a JSON-RPC request body calls (``tools/call``).

    Handles single messages and batches. Anything unparseable yields an
    empty set; the MCP SDK rejects such bodies itself.
    """
    try:
        message = json.loads(body)
    except (ValueError, UnicodeDecodeError):
        return set()
    messages = message if isinstance(message, list) else [message]
    names = set()
    for item in messages:
        if not isinstance(item, dict) or item.get("method") != "tools/call":
            continue
        params = item.get("params")
        if isinstance(params, dict) and isinstance(params.get("name"), str):
            names.add(params["name"])
    return names


def protected_resource_metadata_url(request) -> str:
    """Absolute URL of the RFC 9728 metadata document for ``/mcp``."""
    return request.build_absolute_uri(reverse("oauth_protected_resource_rfc9728"))


def _jsonrpc_method(body: bytes) -> str:
    """JSON-RPC method of a request body, for logs (never the params)."""
    try:
        message = json.loads(body)
    except (ValueError, UnicodeDecodeError):
        return "<unparseable>"
    if isinstance(message, list):
        return f"<batch of {len(message)}>"
    if not isinstance(message, dict):
        return f"<{type(message).__name__}>"
    if "method" not in message:
        return "<response>" if "result" in message or "error" in message else "<none>"
    return str(message["method"])[:64]


def log_rejected_mcp_request(request, response) -> None:
    """Log why the MCP endpoint answered with a 4xx status.

    Requests are rejected before any tool runs: by DRF (a body that is not
    JSON fails in OAuth2 authentication, which reads ``request.POST``; bad
    credentials; throttling) or by the MCP SDK (a body that is not one
    JSON-RPC message, an unsupported ``MCP-Protocol-Version``). Only the
    response body says why, and no access log keeps it. Logs that reason
    with the JSON-RPC method and the transport headers. Tool arguments are
    not logged.
    """
    try:
        body = request.body
    except Exception:  # body stream already consumed
        body = b""
    if getattr(response, "data", None) is not None:  # DRF error, not rendered yet
        reason = json.dumps(response.data, ensure_ascii=False)[:300]
    elif getattr(response, "streaming", False):
        reason = ""
    else:
        reason = response.content[:300].decode("utf-8", "replace")
    logger.warning(
        "mcp_request_rejected status=%s method=%s protocol_version=%s "
        "content_type=%s accept=%s body_bytes=%s user_agent=%s reason=%s",
        response.status_code,
        _jsonrpc_method(body),
        request.headers.get("MCP-Protocol-Version", "-"),
        request.headers.get("Content-Type", "-"),
        request.headers.get("Accept", "-"),
        len(body),
        request.headers.get("User-Agent", "-")[:80],
        reason,
    )


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

    def authenticate_header(self, request):
        """Bearer challenge that points MCP clients at the OAuth metadata.

        The MCP authorization spec requires a 401 to carry
        ``resource_metadata`` (RFC 9728) so that the client can find the
        authorization server and start the sign-in.
        """
        header = super().authenticate_header(request)
        return (
            f'{header},resource_metadata="{protected_resource_metadata_url(request)}"'
        )


class OLDPMCPView(MCPServerStreamableHttpView):
    """MCP Streamable HTTP endpoint for OLDP.

    Supports anonymous access (no authentication required) with rate limiting.
    Authenticated users (via OAuth2 or API token) get higher rate limits.

    **POST-only by design.** The Streamable HTTP transport allows a server to
    expose a GET SSE stream for server-initiated messages; this one does not,
    because every tool here is request/response and nothing is pushed. GET is
    answered with ``405`` and an ``Allow: POST, DELETE, OPTIONS`` header, which
    is the spec-correct way to decline it -- a conforming client falls back to
    POST-only operation. The 405s in the access log (1,142 over a 30-day window
    against 13.3k successful calls) are clients probing for that stream, not
    failures.

    Keep this contract deliberate: adding a GET stream later is a transport
    change, not a routing tweak, because it implies session resumability and
    server-initiated delivery.
    """

    authentication_classes = [
        StrictOAuth2Authentication,
        CombinedTokenAuthentication,
        SessionAuthentication,
    ]
    permission_classes = [AllowAny]
    throttle_classes = MCP_THROTTLE_CLASSES
    http_method_names = ["post", "delete", "options"]

    def dispatch(self, request, *args, **kwargs):
        """Return method errors before DRF content negotiation runs."""
        if request.method == "GET":
            return HttpResponseNotAllowed(["POST", "DELETE"])
        return super().dispatch(request, *args, **kwargs)

    def finalize_response(self, request, response, *args, **kwargs):
        """Log the reason for every 4xx answer (SDK, auth, parse, throttle)."""
        response = super().finalize_response(request, response, *args, **kwargs)
        if 400 <= response.status_code < 500:
            log_rejected_mcp_request(request, response)
        return response

    def check_permissions(self, request):
        """Ask anonymous callers of sign-in-only tools to sign in (HTTP 401).

        The endpoint itself is open to anonymous callers. A ``tools/call``
        for a tool in ``SIGN_IN_REQUIRED_TOOLS`` without credentials raises
        ``NotAuthenticated``; DRF answers it with HTTP 401 and the
        ``WWW-Authenticate`` challenge of ``StrictOAuth2Authentication``.
        """
        super().check_permissions(request)
        if getattr(request.user, "is_authenticated", False):
            return
        if request.method != "POST":
            return
        try:
            body = request.body
        except Exception:  # stream already consumed; the tool refuses itself
            return
        blocked = sorted(_called_tools(body) & SIGN_IN_REQUIRED_TOOLS)
        if blocked:
            raise NotAuthenticated(
                f"{', '.join(blocked)} requires a signed-in connection. Sign in "
                "with your OLDP account (OAuth) or send an API token, then retry."
            )

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


@require_GET
def mcp_registry_auth_view(request):
    """Serve the MCP Registry domain-verification record.

    The official MCP Registry (registry.modelcontextprotocol.io) verifies
    ownership of a reverse-DNS namespace by fetching
    ``/.well-known/mcp-registry-auth`` and checking the public key in it
    against the signature from ``mcp-publisher login http``. The record
    comes from the ``MCP_REGISTRY_AUTH`` setting.

    Returns:
        The record as ``text/plain``, or 404 when the setting is empty.
    """
    record = (getattr(settings, "MCP_REGISTRY_AUTH", "") or "").strip()
    if not record:
        raise Http404("MCP registry auth is not configured")
    return HttpResponse(record + "\n", content_type="text/plain; charset=utf-8")
