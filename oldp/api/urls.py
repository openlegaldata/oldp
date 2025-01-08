from django.urls import re_path
from django.urls import include
from rest_framework import routers
from rest_framework.authtoken import views as authtoken_views

from oldp.api.views import CourtViewSet, CityViewSet, StateViewSet, CountryViewSet
from oldp.apps.accounts.api_views import UserViewSet
from oldp.apps.annotations.api_views import CaseAnnotationViewSet, AnnotationLabelViewSet, CaseMarkerViewSet
from oldp.apps.cases.api_views import CaseViewSet, CaseSearchViewSet
from oldp.apps.laws.api_views import LawSearchViewSet, LawBookViewSet, LawViewSet
from . import schema_view

router = routers.DefaultRouter()

# Search views (must be declared before model views)
router.register(r'laws/search', LawSearchViewSet, basename='law-search')
router.register(r'cases/search', CaseSearchViewSet, basename='case-search')

# Model views
router.register(r'users', UserViewSet)
router.register(r'laws', LawViewSet)
router.register(r'law_books', LawBookViewSet)
router.register(r'cases', CaseViewSet)
router.register(r'courts', CourtViewSet)
router.register(r'cities', CityViewSet)
router.register(r'states', StateViewSet)
router.register(r'countries', CountryViewSet)
router.register(r'annotation_labels', AnnotationLabelViewSet)
router.register(r'case_annotations', CaseAnnotationViewSet)
router.register(r'case_markers', CaseMarkerViewSet)

urlpatterns = [
    re_path(r'^schema(?P<format>\.json|\.yaml)$', schema_view.without_ui(cache_timeout=None), name='schema-json'),
    re_path(r'^schema/$', schema_view.with_ui('swagger', cache_timeout=None), name='schema-swagger-ui'),
    re_path(r'^docs/$', schema_view.with_ui('redoc', cache_timeout=None), name='schema-redoc'),
    re_path(r'^token-auth/', authtoken_views.obtain_auth_token),
    re_path(r'^', include(router.urls)),
]
