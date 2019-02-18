import coreapi
import coreschema
from django_filters.rest_framework import DjangoFilterBackend
from drf_haystack.filters import HaystackFilter
from drf_haystack.generics import HaystackGenericAPIView
from rest_framework import viewsets
from rest_framework.mixins import ListModelMixin
from rest_framework.permissions import AllowAny
from rest_framework.viewsets import ViewSetMixin

from oldp.api import SmallResultsSetPagination
from oldp.apps.laws.models import Law, LawBook
from oldp.apps.laws.search_indexes import LawIndex
from oldp.apps.laws.serializers import LawSerializer, LawBookSerializer, LawSearchSerializer
from oldp.apps.search.filters import SearchSchemaFilter


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


class LawSearchSchemaFilter(SearchSchemaFilter):
    search_index_class = LawIndex

    def get_default_schema_fields(self):
        return [
            # Search query field is required
            coreapi.Field(
                name='text',
                location='query',
                required=True,
                schema=coreschema.String(description='Search query on text content (Lucence syntax support).'),
            )
        ]


class LawSearchViewSet(ListModelMixin, ViewSetMixin, HaystackGenericAPIView):
    """
    Search view
    """
    permission_classes = (AllowAny,)
    pagination_class = SmallResultsSetPagination  # limit page (other content field blows up response size)
    index_models = [
        Law
    ]
    serializer_class = LawSearchSerializer
    filter_backends = (HaystackFilter, LawSearchSchemaFilter,)
