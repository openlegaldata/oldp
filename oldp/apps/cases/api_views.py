from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import viewsets

from oldp.apps.cases.models import Case
from oldp.apps.cases.serializers import CaseSerializer


class CaseViewSet(viewsets.ModelViewSet):
    queryset = Case.get_queryset().only('id', 'court_id', 'file_number', 'date', 'type', 'ecli', 'content')
    serializer_class = CaseSerializer

    filter_backends = (DjangoFilterBackend,)
    filter_fields = ('slug', 'file_number', 'court_id')
    # filterset_class = CaseAPIFilter
