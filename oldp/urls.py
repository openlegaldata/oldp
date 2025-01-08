from django.conf import settings
from django.urls import include, re_path

from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.flatpages import views as flatpages_views
from django.contrib.sitemaps import views as sitemaps_views
from django.urls import path
from django.views.decorators.cache import cache_page
from django.views.generic import RedirectView, TemplateView

from oldp.apps import cases
from oldp.apps.cases.sitemaps import CaseSitemap
from oldp.apps.courts.sitemaps import CourtSitemap
from oldp.apps.laws.sitemaps import LawSitemap
from oldp.apps.search.views import CustomSearchView, autocomplete_view

# Error handlers
handler500 = 'oldp.apps.homepage.views.error500_view'
handler404 = 'oldp.apps.homepage.views.error404_view'
handler403 = 'oldp.apps.homepage.views.error_permission_denied_view'
handler400 = 'oldp.apps.homepage.views.error_bad_request_view'


urlpatterns = [
    # Admin
    re_path(r'^admin/', admin.site.urls),

    # Apps
    re_path(r'^case/', include('oldp.apps.cases.urls')),
    re_path(r'^c/(?P<pk>[0-9]+)$', cases.views.short_url_view, name='cases_short_url'),

    re_path(r'^law/', include('oldp.apps.laws.urls')),
    re_path(r'^court/', include('oldp.apps.courts.urls')),
    re_path(r'^accounts/', include('oldp.apps.accounts.urls')),
    re_path(r'^accounts/', include('allauth.urls')),
    re_path(r'^contact/', include('oldp.apps.contact.urls')),
    re_path(r'^search/autocomplete', autocomplete_view),
    re_path(r'^search/', CustomSearchView.as_view(), name='haystack_search'),
    re_path(r'^sources/', include('oldp.apps.sources.urls')),

    # Files
    re_path(r'^favicon\.ico$', RedirectView.as_view(url='/static/favicon.ico', permanent=True)),
    re_path(r'^robots\.txt$', TemplateView.as_view(template_name='robots.txt', content_type='text/plain')),

    # Third-party apps
    # re_path(r'^tellme/', include("tellme.urls")),

    # API
    re_path(r'^api/', include('oldp.api.urls')),

    # Homepage
    re_path(r'^', include('oldp.apps.homepage.urls')),

    re_path(r'^pages(?P<url>.*/)$', flatpages_views.flatpage, name='flatpages'),

] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

# Sitemaps
sitemaps = {
    'court': CourtSitemap(),
    'case': CaseSitemap(),
    'law': LawSitemap(),
}

urlpatterns += [
    path('sitemap.xml', cache_page(86400)(sitemaps_views.index), {'sitemaps': sitemaps}),
    path('sitemap-<section>.xml', cache_page(86400)(sitemaps_views.sitemap), {'sitemaps': sitemaps}, name='django.contrib.sitemaps.views.sitemap')
]


# DEBUG only views
if settings.DEBUG:
    # Django debug toolbar
    import debug_toolbar
    urlpatterns = [
        re_path(r'^__debug__/', include(debug_toolbar.urls)),
    ] + urlpatterns

# """
# URL configuration for oldp project.

# The `urlpatterns` list routes URLs to views. For more information please see:
#     https://docs.djangoproject.com/en/5.0/topics/http/urls/
# Examples:
# Function views
#     1. Add an import:  from my_app import views
#     2. Add a URL to urlpatterns:  path('', views.home, name='home')
# Class-based views
#     1. Add an import:  from other_app.views import Home
#     2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
# Including another URLconf
#     1. Import the include() function: from django.urls import include, path
#     2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
# """
# from django.contrib import admin
# from django.urls import path

# urlpatterns = [
#     path('admin/', admin.site.urls),
# ]
