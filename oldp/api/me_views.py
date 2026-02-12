"""API viewsets for /me/ endpoints.

Provides read-only access to resources created by the authenticated API token.
"""

from rest_framework import mixins, viewsets
from rest_framework.permissions import IsAuthenticated

from oldp.apps.cases.models import Case
from oldp.apps.cases.serializers import CaseSerializer
from oldp.apps.courts.models import Court
from oldp.apps.courts.serializers import CourtSerializer
from oldp.apps.laws.models import Law, LawBook
from oldp.apps.laws.serializers import LawBookSerializer, LawSerializer


class MyItemsMixin:
    """Mixin that filters queryset to items created by the authenticated token."""

    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = super().get_queryset()
        token = self.request.auth
        if token is None:
            return qs.none()
        return qs.filter(created_by_token=token).select_related("created_by_token")


class MyCaseViewSet(MyItemsMixin, mixins.ListModelMixin, viewsets.GenericViewSet):
    """List cases created by the authenticated API token."""

    queryset = Case.objects.all().order_by("-created_date")
    serializer_class = CaseSerializer

    def get_queryset(self):
        return super().get_queryset().select_related("court")


class MyLawBookViewSet(MyItemsMixin, mixins.ListModelMixin, viewsets.GenericViewSet):
    """List law books created by the authenticated API token."""

    queryset = LawBook.objects.all().order_by("-id")
    serializer_class = LawBookSerializer


class MyLawViewSet(MyItemsMixin, mixins.ListModelMixin, viewsets.GenericViewSet):
    """List laws created by the authenticated API token."""

    queryset = Law.objects.all().order_by("-id")
    serializer_class = LawSerializer


class MyCourtViewSet(MyItemsMixin, mixins.ListModelMixin, viewsets.GenericViewSet):
    """List courts created by the authenticated API token."""

    queryset = Court.objects.all().order_by("-id")
    serializer_class = CourtSerializer
