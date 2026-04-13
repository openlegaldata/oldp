"""MCP endpoint view with OAuth2 authentication and MCP-specific throttling."""

from mcp_server.views import MCPServerStreamableHttpView
from oauth2_provider.contrib.rest_framework import OAuth2Authentication
from rest_framework.authentication import SessionAuthentication
from rest_framework.permissions import AllowAny

from oldp.apps.accounts.authentication import CombinedTokenAuthentication
from oldp.apps.mcp.throttles import MCPAnonThrottle, MCPUserThrottle


class OLDPMCPView(MCPServerStreamableHttpView):
    """MCP Streamable HTTP endpoint for OLDP.

    Supports anonymous access (no authentication required) with rate limiting.
    Authenticated users (via OAuth2 or API token) get higher rate limits.
    """

    authentication_classes = [
        OAuth2Authentication,
        CombinedTokenAuthentication,
        SessionAuthentication,
    ]
    permission_classes = [AllowAny]
    throttle_classes = [MCPAnonThrottle, MCPUserThrottle]
