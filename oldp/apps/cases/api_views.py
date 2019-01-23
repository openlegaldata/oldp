from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import viewsets

from oldp.apps.cases.models import Case
from oldp.apps.cases.serializers import CaseSerializer


class CaseViewSet(viewsets.ModelViewSet):
    queryset = Case.get_queryset()
    serializer_class = CaseSerializer

    filter_backends = (DjangoFilterBackend,)
    filter_fields = ('slug', 'file_number', 'court_id')
