from django.conf import settings
from django.conf.urls import url

from oldp.utils.cache_per_user import cache_per_user
from . import views

app_name = 'courts'
urlpatterns = [
    url(r'^$', cache_per_user(settings.CACHE_TTL)(views.CourtListView.as_view()), name='index'),
    url(r'^state/(?P<state_slug>[-a-z0-9]+)/$', cache_per_user(settings.CACHE_TTL)(views.CourtListView.as_view()),
        name='index_state'),

    url(r'^(?P<court_slug>[-a-z0-9]+)/$', cache_per_user(settings.CACHE_TTL)(views.CourtCasesListView.as_view()),
        name='detail'),
]
