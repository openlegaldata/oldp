from django.conf import settings
from drf_yasg import openapi
from drf_yasg.views import get_schema_view
from rest_framework.exceptions import NotFound
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import DjangoModelPermissionsOrAnonReadOnly

from oldp.utils.cached_count_paginator import CachedCountPaginator

schema_view = get_schema_view(
    openapi.Info(
        title="Open Legal Data API",
        default_version="v1",
        description="With the Open Legal Data API you can access various data from the legal domain, e.g. law text or "
        "case files. The data may be used for semantic analysis or to create statistics. "
        "For more information visit our website. https://openlegaldata.io/",
        terms_of_service="https://openlegaldata.io/",
        contact=openapi.Contact(email="hello@openlegaldata.io"),
        license=openapi.License(name="MIT License"),
    ),
    validators=["flex", "ssv"],
    public=True,
    permission_classes=(DjangoModelPermissionsOrAnonReadOnly,),
)


class SmallResultsSetPagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = "page_size"
    max_page_size = 1000
    django_paginator_class = CachedCountPaginator

    def paginate_queryset(self, queryset, request, view=None):
        page_number = request.query_params.get(self.page_query_param, 1)
        try:
            page_number = int(page_number)
        except (TypeError, ValueError):
            page_number = 1
        if page_number > settings.PAGINATE_UNTIL:
            raise NotFound(
                f"Page {page_number} exceeds maximum of {settings.PAGINATE_UNTIL}. "
                f"For bulk access use {settings.BULK_EXPORT_URL}"
            )
        return super().paginate_queryset(queryset, request, view)
