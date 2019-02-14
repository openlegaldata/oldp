from django_filters.rest_framework import DjangoFilterBackend
from drf_haystack.viewsets import HaystackViewSet
from rest_framework import viewsets
from rest_framework.permissions import AllowAny

from oldp.api import SmallResultsSetPagination
from oldp.apps.laws.models import Law, LawBook
from oldp.apps.laws.serializers import LawSerializer, LawBookSerializer, LawSearchSerializer


class LawViewSet(viewsets.ModelViewSet):
    queryset = Law.objects.all().order_by('order')
    serializer_class = LawSerializer

    filter_backends = (DjangoFilterBackend,)
    filter_fields = ('book_id', 'book__latest', 'book__revision_date')


class LawBookViewSet(viewsets.ModelViewSet):
    queryset = LawBook.objects.all().order_by('code')
    serializer_class = LawBookSerializer

    filter_backends = (DjangoFilterBackend,)
    filter_fields = ('slug', 'code', 'latest', 'revision_date')


class LawSearchViewSet(HaystackViewSet):
    permission_classes = (AllowAny,)
    pagination_class = SmallResultsSetPagination  # limit page (other content field blows up response size)
    index_models = [
        Law
    ]
    serializer_class = LawSearchSerializer

    def get_queryset(self, *args):
        return super().get_queryset(*args) #.filter(facet_model_name='Law')
