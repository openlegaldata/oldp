"""OLDP URL Configuration"""

from django.conf import settings
from django.conf.urls import include, url
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.flatpages import views as flatpages_views
from django.views.generic import RedirectView, TemplateView
from rest_framework.authtoken import views as authtoken_views

from oldp import api
from oldp.api import schema_view
from oldp.apps.search.views import search_view as search_index

handler404 = 'oldp.apps.homepage.views.error404_view'
handler500 = 'oldp.apps.homepage.views.error500_view'
handler403 = 'oldp.apps.homepage.views.error_permission_denied_view'
handler400 = 'oldp.apps.homepage.views.error_bad_request_view'

favicon_view = RedirectView.as_view(url='/static/favicon.ico', permanent=True)
robots_view = RedirectView.as_view(url='/static/favicon.ico', permanent=True)


urlpatterns = [
    # Admin
    url(r'^admin/', admin.site.urls),

    # Apps
    url(r'^case/', include('oldp.apps.cases.urls')),
    url(r'^law/', include('oldp.apps.laws.urls')),
    url(r'^court/', include('oldp.apps.courts.urls')),
    url(r'^accounts/', include('oldp.apps.accounts.urls')),
    url(r'^accounts/', include('allauth.urls')),
    url(r'^contact/', include('oldp.apps.contact.urls')),
    url(r'^search/', search_index, name='search'),

    # Files
    url(r'^favicon\.ico$', favicon_view),
    url(r'^robots\.txt$', TemplateView.as_view(template_name='robots.txt', content_type='text/plain')),

    # Third-party apps
    url(r'^tellme/', include("tellme.urls")),

    # API
    url(r'^api/', include(api.router.urls)),
    url(r'^api-schema(?P<format>\.json|\.yaml)$', schema_view.without_ui(cache_timeout=None), name='schema-json'),
    url(r'^api-schema/$', schema_view.with_ui('swagger', cache_timeout=None), name='schema-swagger-ui'),
    url(r'^api-docs/$', schema_view.with_ui('redoc', cache_timeout=None), name='schema-redoc'),

    # url(r'^api/auth/', include('rest_framework.urls', namespace='rest_framework')),
    url(r'^api/token-auth/', authtoken_views.obtain_auth_token),

    # Homepage
    url(r'^', include('oldp.apps.homepage.urls')),

    url(r'^pages(?P<url>.*/)$', flatpages_views.flatpage, name='flatpages')

] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

# Django debug toolbar
if settings.DEBUG:
    import debug_toolbar
    urlpatterns = [
        url(r'^__debug__/', include(debug_toolbar.urls)),
    ] + urlpatterns
