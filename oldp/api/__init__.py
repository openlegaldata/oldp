from drf_yasg import openapi
from drf_yasg.views import get_schema_view
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import DjangoModelPermissionsOrAnonReadOnly


schema_view = get_schema_view(
    openapi.Info(
        title="Open Legal Data API",
        default_version='v1',
        description="With the Open Legal Data API you can access various data from the legal domain, e.g. law text or "
                    "case files. The data may be used for semantic analysis or to create statistics. "
                    "For more information visit our website. https://openlegaldata.io/",
        terms_of_service="https://openlegaldata.io/",
        contact=openapi.Contact(email="hello@openlegaldata.io"),
        license=openapi.License(name="MIT License"),
    ),
    validators=['flex', 'ssv'],
    public=True,
    permission_classes=(DjangoModelPermissionsOrAnonReadOnly,),
)


class SmallResultsSetPagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = 'page_size'
    max_page_size = 1000
