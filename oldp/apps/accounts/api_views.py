from django.contrib.auth.models import User
from rest_framework import viewsets, permissions
from rest_framework.decorators import action
from rest_framework.response import Response

from oldp.apps.accounts.serializers import UserSerializer


class UserViewSet(viewsets.ModelViewSet):
    """
    API endpoint that allows a user's profile to be viewed or edited.
    """
    permission_classes = (permissions.IsAuthenticated, )
    queryset = User.objects.order_by('pk').all()
    serializer_class = UserSerializer

    http_method_names = ['get', 'head', 'options']  # Read-only endpoint

    @action(detail=False)
    def me(self, request):
        """
        Show current user (useful for verifying API key)
        """
        queryset = User.objects.filter(pk=request.user.id)

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

