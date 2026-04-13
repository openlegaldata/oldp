"""URL configuration for MCP server, OAuth, and well-known endpoints."""

from django.urls import include, path

from oldp.apps.mcp.oauth_views import (
    DynamicClientRegistrationView,
    oauth_authorization_server_view,
    oauth_protected_resource_view,
)
from oldp.apps.mcp.views import OLDPMCPView

urlpatterns = [
    # MCP endpoint (Model Context Protocol - Streamable HTTP)
    path("mcp", OLDPMCPView.as_view(), name="mcp_endpoint"),
    # OAuth2 endpoints for MCP connector authentication
    path("oauth/", include("oauth2_provider.urls", namespace="oauth2_provider")),
    path(
        "oauth/register/",
        DynamicClientRegistrationView.as_view(),
        name="oauth_dcr",
    ),
    # Well-known OAuth discovery endpoints
    path(
        ".well-known/oauth-protected-resource",
        oauth_protected_resource_view,
        name="oauth_protected_resource",
    ),
    path(
        ".well-known/oauth-authorization-server",
        oauth_authorization_server_view,
        name="oauth_authorization_server",
    ),
]
