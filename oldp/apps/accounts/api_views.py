from django.contrib.auth.models import User
from rest_framework import authentication, permissions, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from oldp.apps.accounts.authentication import CombinedTokenAuthentication
from oldp.apps.accounts.models import APIToken
from oldp.apps.accounts.serializers import UserSerializer


class UserViewSet(viewsets.ModelViewSet):
    """API endpoint that allows a user's profile to be viewed or edited."""

    permission_classes = (permissions.IsAuthenticated,)
    queryset = User.objects.order_by("pk").all()
    serializer_class = UserSerializer

    http_method_names = ["get", "head", "options"]  # Read-only endpoint

    @action(detail=False)
    def me(self, request):
        """Show current user (useful for verifying API key)"""
        queryset = User.objects.filter(pk=request.user.id)

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)


class MeView(APIView):
    """API endpoint that returns details about the authenticated user.

    Returns user info, authentication type, and token permissions.
    Only accessible to authenticated users.
    """

    authentication_classes = (
        CombinedTokenAuthentication,
        authentication.SessionAuthentication,
    )
    permission_classes = (permissions.IsAuthenticated,)

    def get(self, request):
        user = request.user
        auth = request.auth

        # Determine authentication type
        if isinstance(auth, APIToken):
            auth_type = "api_token"
            token_info = {
                "name": auth.name,
                "permissions": auth.get_permissions(),
                "created": auth.created.isoformat(),
                "last_used": auth.last_used.isoformat() if auth.last_used else None,
                "expires_at": auth.expires_at.isoformat() if auth.expires_at else None,
            }
        elif auth is not None:
            auth_type = "token"
            token_info = None
        else:
            auth_type = "session"
            token_info = None

        data = {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "is_staff": user.is_staff,
            "is_superuser": user.is_superuser,
            "auth_type": auth_type,
        }

        if token_info is not None:
            data["token"] = token_info

        return Response(data)
