from django.db.models import Q
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import viewsets
from rest_framework.filters import OrderingFilter

from oldp.api.permissions import OwnerPrivatePermission
from oldp.apps.annotations.filters import AnnotationLabelFilter, CaseAnnotationFilter
from oldp.apps.annotations.models import AnnotationLabel, CaseAnnotation
from oldp.apps.annotations.serializers import AnnotationLabelSerializer, CaseAnnotationSerializer


class AnnotationLabelViewSet(viewsets.ModelViewSet):
    queryset = AnnotationLabel.objects.all()
    serializer_class = AnnotationLabelSerializer
    permission_classes = (OwnerPrivatePermission, )

    filter_backends = (OrderingFilter, DjangoFilterBackend,)
    filterset_class = AnnotationLabelFilter
    ordering_fields = ('created_at', 'updated_at', )

    def get_queryset(self):
        # public items or user is owner
        if self.request.user.is_authenticated:
            if self.request.user.is_staff:
                return AnnotationLabel.objects.all()
            else:
                return AnnotationLabel.objects.filter(Q(private=False) | Q(owner=self.request.user))
        else:
            return AnnotationLabel.objects.filter(private=False)

    def perform_destroy(self, instance):
        super().perform_destroy(instance)

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)


class CaseAnnotationViewSet(viewsets.ModelViewSet):
    queryset = CaseAnnotation.objects.select_related('belongs_to__court').all()
    serializer_class = CaseAnnotationSerializer

    filter_backends = (DjangoFilterBackend,)
    filterset_class = CaseAnnotationFilter

    # def get_queryset(self):
    #     return AnnotationLabel.objects.all()

    def perform_destroy(self, instance):
        super().perform_destroy(instance)
