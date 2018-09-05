from django.conf import settings
from django.conf.urls import url
from django.views.decorators.cache import cache_page

from . import views

app_name = 'courts'
urlpatterns = [
    url(r'^$', cache_page(settings.CACHE_TTL)(views.CourtListView.as_view()), name='index'),
    url(r'^state/(?P<state_slug>[-a-z0-9]+)/$', cache_page(settings.CACHE_TTL)(views.CourtListView.as_view()),
        name='index_state'),

    url(r'^(?P<court_slug>[-a-z0-9]+)/$', cache_page(settings.CACHE_TTL)(views.CourtCasesListView.as_view()),
        name='detail'),
]
