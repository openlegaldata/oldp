import coreapi
import coreschema
from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_page
from django_filters.rest_framework import DjangoFilterBackend
from drf_haystack.filters import HaystackFilter
from drf_haystack.generics import HaystackGenericAPIView
from rest_framework import viewsets
from rest_framework.filters import OrderingFilter
from rest_framework.mixins import ListModelMixin
from rest_framework.permissions import AllowAny
from rest_framework.viewsets import ViewSetMixin

from oldp.api import SmallResultsSetPagination
from oldp.apps.cases.filters import CaseAPIFilter
from oldp.apps.cases.models import Case
from oldp.apps.cases.search_indexes import CaseIndex
from oldp.apps.cases.serializers import CaseSerializer, CASE_API_FIELDS, CaseSearchSerializer
from oldp.apps.search.filters import SearchSchemaFilter


class CaseViewSet(viewsets.ModelViewSet):
    """
    List view for cases
    """
    pagination_class = SmallResultsSetPagination  # limit page (other content field blows up response size)
    queryset = Case.get_queryset()
    serializer_class = CaseSerializer
    # lookup_field = 'slug'

    filter_backends = (OrderingFilter, DjangoFilterBackend, )
    filterset_class = CaseAPIFilter
    ordering_fields = ('date', )

    @method_decorator(cache_page(60))
    def dispatch(self, *args, **kwargs):
        return super().dispatch(*args, **kwargs)

    def get_queryset(self):
        return Case.get_queryset()\
            .select_related('court')\
            .only(*CASE_API_FIELDS)


class CaseSearchSchemaFilter(SearchSchemaFilter):
    search_index_class = CaseIndex

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


class CaseSearchViewSet(ListModelMixin, ViewSetMixin, HaystackGenericAPIView):
    """
    Search view (list only)
    """
    permission_classes = (AllowAny,)
    pagination_class = SmallResultsSetPagination  # limit page (other content field blows up response size)
    index_models = [
        Case
    ]
    serializer_class = CaseSearchSerializer
    filter_backends = (HaystackFilter, CaseSearchSchemaFilter,)

