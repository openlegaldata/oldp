from django.db.models import Q
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import viewsets
from rest_framework.exceptions import ValidationError
from rest_framework.filters import OrderingFilter

from oldp.api.permissions import OwnerPrivatePermission
from oldp.apps.annotations.filters import AnnotationLabelFilter, CaseAnnotationFilter
from oldp.apps.annotations.models import AnnotationLabel, CaseAnnotation, CaseMarker
from oldp.apps.annotations.serializers import (
    AnnotationLabelSerializer,
    CaseAnnotationSerializer,
    CaseMarkerSerializer,
)


class AnnotationLabelViewSet(viewsets.ModelViewSet):
    """ViewSet for annotation labels.

    Labels categorize case annotations (e.g. "Important", "Review").
    Private labels are only visible to their owner; public labels are visible to all.
    Staff users can see all labels.
    """

    queryset = AnnotationLabel.objects.all()
    serializer_class = AnnotationLabelSerializer
    permission_classes = (OwnerPrivatePermission,)

    filter_backends = (
        OrderingFilter,
        DjangoFilterBackend,
    )
    filterset_class = AnnotationLabelFilter
    ordering_fields = (
        "created_at",
        "updated_at",
    )

    def get_queryset(self):
        qs = AnnotationLabel.objects.select_related("owner").order_by("owner")

        # public items or user is owner
        if hasattr(self, "request") and self.request.user.is_authenticated:
            if self.request.user.is_staff:
                return qs.all()
            else:
                return qs.filter(Q(private=False) | Q(owner=self.request.user))
        else:
            return qs.filter(private=False)

    def perform_create(self, serializer):
        if AnnotationLabel.objects.filter(
            owner=self.request.user, slug=serializer.validated_data.get("slug")
        ).exists():
            raise ValidationError(
                {
                    "slug": "The fields owner, slug must make a unique set. (slug: `%s`, owner: %s)"
                    % (
                        serializer.validated_data.get("slug"),
                        self.request.user.username,
                    )
                }
            )
        else:
            serializer.save(owner=self.request.user)


class CaseAnnotationViewSet(viewsets.ModelViewSet):
    """ViewSet for case annotations.

    Annotations attach a label and optional text to a specific case.
    Visibility follows the label's privacy setting: annotations with private
    labels are only visible to the label owner.
    """

    queryset = CaseAnnotation.objects.select_related(
        "belongs_to__court", "label", "label__owner"
    ).order_by("label")
    serializer_class = CaseAnnotationSerializer
    permission_classes = (OwnerPrivatePermission,)

    filter_backends = (DjangoFilterBackend,)
    filterset_class = CaseAnnotationFilter

    def filter_queryset_by_permission(self, queryset):
        # public items or user is owner
        if hasattr(self, "request") and self.request.user.is_authenticated:
            if self.request.user.is_staff:
                return queryset.all()
            else:
                return queryset.filter(
                    Q(label__private=False) | Q(label__owner=self.request.user)
                )
        else:
            return queryset.filter(label__private=False)

    def get_queryset(self):
        return self.filter_queryset_by_permission(self.queryset)


class CaseMarkerViewSet(viewsets.ModelViewSet):
    """ViewSet for case markers.

    Markers highlight specific text ranges within a case document,
    identified by start/end character offsets and associated with an annotation label.
    """

    queryset = CaseMarker.objects.select_related("belongs_to__court", "label").order_by(
        "label"
    )
    serializer_class = CaseMarkerSerializer
    permission_classes = (OwnerPrivatePermission,)

    filter_backends = (DjangoFilterBackend,)
    filterset_class = CaseAnnotationFilter
