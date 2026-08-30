from django.conf import settings
from drf_yasg import openapi
from drf_yasg.views import get_schema_view
from rest_framework.exceptions import NotFound
from rest_framework.pagination import LimitOffsetPagination, PageNumberPagination
from rest_framework.permissions import DjangoModelPermissionsOrAnonReadOnly

from oldp.utils.cached_count_paginator import (
    CachedCountPaginator,
    cached_queryset_count,
)

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


def _reject_deep_offset(request, max_offset):
    offset = request.query_params.get("offset")
    if offset is None:
        return
    try:
        offset = int(offset)
    except (TypeError, ValueError):
        return
    if offset > max_offset:
        raise NotFound(
            f"Offset {offset} exceeds maximum of {max_offset}. "
            f"For bulk access use {settings.BULK_EXPORT_URL}"
        )


class SmallResultsSetPagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = "page_size"
    max_page_size = 1000
    django_paginator_class = CachedCountPaginator

    def paginate_queryset(self, queryset, request, view=None):
        _reject_deep_offset(request, settings.PAGINATE_UNTIL * self.max_page_size)
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


class CappedLimitOffsetPagination(LimitOffsetPagination):
    default_limit = 50
    max_limit = 1000

    def paginate_queryset(self, queryset, request, view=None):
        _reject_deep_offset(request, settings.PAGINATE_UNTIL * self.max_limit)
        return super().paginate_queryset(queryset, request, view)

    def get_count(self, queryset):
        """Cache the pagination ``COUNT(*)``.

        ``SmallResultsSetPagination`` gets this for free via
        ``django_paginator_class = CachedCountPaginator``, but
        ``LimitOffsetPagination`` never builds a Django ``Paginator`` — it
        calls ``queryset.count()`` here directly, so the cache was bypassed on
        every endpoint using the *default* pagination class (references, laws,
        courts...). The prod slow log showed the cost: a bare
        ``SELECT COUNT(*) FROM references_reference`` examining 18.6M rows at
        ~3.3s a call (internal-tools#5).
        """
        return cached_queryset_count(queryset)
