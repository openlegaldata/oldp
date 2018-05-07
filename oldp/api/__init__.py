from drf_yasg import openapi
from drf_yasg.views import get_schema_view
from rest_framework import routers, permissions

from oldp.api.views import CourtViewSet, CityViewSet, StateViewSet, CountryViewSet, LawViewSet, LawBookViewSet, \
    CaseViewSet

# Routers provide an easy way of automatically determining the URL conf.
router = routers.DefaultRouter()

router.register(r'laws', LawViewSet)
router.register(r'law_books', LawBookViewSet)
router.register(r'cases', CaseViewSet)
router.register(r'courts', CourtViewSet)
router.register(r'cities', CityViewSet)
router.register(r'states', StateViewSet)
router.register(r'countries', CountryViewSet)


schema_view = get_schema_view(
   openapi.Info(
      title="Open Legal Data API",
      default_version='v1',
      description="With the Open Legal Data API you can access various data from the legal domain, e.g. law text or "
                  "case files. The data may be used for semantic analysis or to create statistics. "
                  "For more information visit our website.",
      terms_of_service="https://openlegaldata.io/",
      contact=openapi.Contact(email="api@openlegaldata.io"),
      license=openapi.License(name="MIT License"),
   ),
   validators=['flex', 'ssv'],
   public=True,
   permission_classes=(permissions.DjangoModelPermissionsOrAnonReadOnly,),
)
