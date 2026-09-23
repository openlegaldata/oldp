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
    # Well-known OAuth discovery endpoints.
    #
    # Served at three paths because clients disagree about where to look, and a
    # 404 here makes a spec-compliant client treat the server as having no
    # OAuth support at all:
    #
    #   /.well-known/<doc>          root form, what we have always served
    #   /mcp/.well-known/<doc>      resource-relative; what MCP clients in the
    #                               wild actually request (675 404s in a 30-day
    #                               window against 13.3k successful calls)
    #   /.well-known/<doc>/mcp      RFC 9728 path-insertion form for a resource
    #                               identifier that has a path component
    #
    # All three return identical metadata; the endpoint is a single resource.
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
    path(
        "mcp/.well-known/oauth-protected-resource",
        oauth_protected_resource_view,
        name="mcp_oauth_protected_resource",
    ),
    path(
        "mcp/.well-known/oauth-authorization-server",
        oauth_authorization_server_view,
        name="mcp_oauth_authorization_server",
    ),
    path(
        ".well-known/oauth-protected-resource/mcp",
        oauth_protected_resource_view,
        name="oauth_protected_resource_rfc9728",
    ),
    path(
        ".well-known/oauth-authorization-server/mcp",
        oauth_authorization_server_view,
        name="oauth_authorization_server_rfc9728",
    ),
]
