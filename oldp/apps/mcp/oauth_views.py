"""OAuth 2.0 discovery and Dynamic Client Registration endpoints for MCP.

Provides the well-known endpoints that Claude and other MCP clients use to
discover the OAuth authorization server, and a minimal DCR endpoint (RFC 7591)
for automatic client registration.
"""

import logging
import secrets

from django.http import JsonResponse
from django.views.decorators.http import require_GET
from oauth2_provider.models import get_application_model
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView

logger = logging.getLogger(__name__)

Application = get_application_model()


@require_GET
def oauth_protected_resource_view(request):
    """RFC 8707: OAuth Protected Resource Metadata.

    Tells MCP clients where the authorization server is for this resource.
    """
    base_url = request.build_absolute_uri("/").rstrip("/")
    return JsonResponse(
        {
            "resource": f"{base_url}/mcp",
            "authorization_servers": [base_url],
            "bearer_methods_supported": ["header"],
            "scopes_supported": ["read"],
        }
    )


@require_GET
def oauth_authorization_server_view(request):
    """RFC 8414: OAuth Authorization Server Metadata.

    Returns the OAuth endpoints that MCP clients need to initiate the
    authorization flow.
    """
    base_url = request.build_absolute_uri("/").rstrip("/")
    return JsonResponse(
        {
            "issuer": base_url,
            "authorization_endpoint": f"{base_url}/oauth/authorize/",
            "token_endpoint": f"{base_url}/oauth/token/",
            "registration_endpoint": f"{base_url}/oauth/register/",
            "scopes_supported": ["read"],
            "response_types_supported": ["code"],
            "grant_types_supported": ["authorization_code", "refresh_token"],
            "code_challenge_methods_supported": ["S256"],
            "token_endpoint_auth_methods_supported": [
                "none",
                "client_secret_basic",
                "client_secret_post",
            ],
        }
    )


class DCRThrottle(AnonRateThrottle):
    """Rate limit Dynamic Client Registration to prevent abuse."""

    rate = "10/hour"


class DynamicClientRegistrationView(APIView):
    """RFC 7591: Dynamic Client Registration.

    Allows MCP clients (like Claude) to automatically register as OAuth
    applications. Creates a public client (no client_secret) suitable for
    native/SPA apps using PKCE.
    """

    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [DCRThrottle]

    def post(self, request):
        data = request.data
        client_name = data.get("client_name", "MCP Client")
        redirect_uris = data.get("redirect_uris", [])
        grant_types = data.get("grant_types", ["authorization_code"])
        token_endpoint_auth_method = data.get("token_endpoint_auth_method", "none")

        if not redirect_uris:
            return Response(
                {
                    "error": "invalid_client_metadata",
                    "error_description": "redirect_uris is required",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        if isinstance(redirect_uris, list):
            redirect_uris_str = "\n".join(redirect_uris)
        else:
            redirect_uris_str = str(redirect_uris)

        # Determine client type based on auth method
        if token_endpoint_auth_method == "none":
            client_type = Application.CLIENT_PUBLIC
            client_secret = ""
        else:
            client_type = Application.CLIENT_CONFIDENTIAL
            client_secret = secrets.token_urlsafe(48)

        # Determine authorization grant type
        if "authorization_code" in grant_types:
            auth_grant_type = Application.GRANT_AUTHORIZATION_CODE
        elif "client_credentials" in grant_types:
            auth_grant_type = Application.GRANT_CLIENT_CREDENTIALS
        else:
            auth_grant_type = Application.GRANT_AUTHORIZATION_CODE

        app = Application.objects.create(
            name=client_name,
            client_type=client_type,
            authorization_grant_type=auth_grant_type,
            redirect_uris=redirect_uris_str,
            client_secret=client_secret,
            skip_authorization=False,
        )

        response_data = {
            "client_id": app.client_id,
            "client_name": app.name,
            "redirect_uris": redirect_uris,
            "grant_types": grant_types,
            "token_endpoint_auth_method": token_endpoint_auth_method,
        }

        if client_secret:
            response_data["client_secret"] = client_secret

        logger.info("DCR: registered new OAuth application '%s'", client_name)

        return Response(response_data, status=status.HTTP_201_CREATED)
