from django.conf import settings
from django.urls import include, re_path
from rest_framework import routers
from rest_framework.authtoken import views as authtoken_views

from oldp.api.me_views import (
    MyCaseViewSet,
    MyCourtViewSet,
    MyLawBookViewSet,
    MyLawViewSet,
)
from oldp.api.views import CityViewSet, CountryViewSet, CourtViewSet, StateViewSet
from oldp.apps.accounts.api_views import MeView, UserViewSet
from oldp.apps.annotations.api_views import (
    AnnotationLabelViewSet,
    CaseAnnotationViewSet,
    CaseMarkerViewSet,
)
from oldp.apps.cases.api_views import CaseSearchViewSet, CaseViewSet
from oldp.apps.laws.api_views import LawBookViewSet, LawSearchViewSet, LawViewSet
from oldp.utils.cache_per_user import cache_per_role

from . import schema_view

router = routers.DefaultRouter()

me_router = routers.SimpleRouter()
me_router.register(r"cases", MyCaseViewSet, basename="my-cases")
me_router.register(r"law_books", MyLawBookViewSet, basename="my-law-books")
me_router.register(r"laws", MyLawViewSet, basename="my-laws")
me_router.register(r"courts", MyCourtViewSet, basename="my-courts")

# Search views (must be declared before model views)
router.register(r"laws/search", LawSearchViewSet, basename="law-search")
router.register(r"cases/search", CaseSearchViewSet, basename="case-search")

# Model views
router.register(r"users", UserViewSet)
router.register(r"laws", LawViewSet)
router.register(r"law_books", LawBookViewSet)
router.register(r"cases", CaseViewSet)
router.register(r"courts", CourtViewSet)
router.register(r"cities", CityViewSet)
router.register(r"states", StateViewSet)
router.register(r"countries", CountryViewSet)
router.register(r"annotation_labels", AnnotationLabelViewSet)
router.register(r"case_annotations", CaseAnnotationViewSet)
router.register(r"case_markers", CaseMarkerViewSet)

urlpatterns = [
    re_path(
        r"^schema(?P<format>\.json|\.yaml)$",
        cache_per_role(settings.CACHE_TTL)(schema_view.without_ui(cache_timeout=None)),
        name="schema-json",
    ),
    re_path(
        r"^schema/$",
        cache_per_role(settings.CACHE_TTL)(
            schema_view.with_ui("swagger", cache_timeout=None)
        ),
        name="schema-swagger-ui",
    ),
    re_path(
        r"^docs/$",
        cache_per_role(settings.CACHE_TTL)(
            schema_view.with_ui("redoc", cache_timeout=None)
        ),
        name="schema-redoc",
    ),
    re_path(r"^token-auth/", authtoken_views.obtain_auth_token),
    re_path(r"^me/$", MeView.as_view(), name="api-me"),
    re_path(r"^me/", include(me_router.urls)),
    re_path(r"^", include(router.urls)),
]
