from django.conf import settings
from django.urls import re_path

from oldp.apps.courts.views import CourtAutocomplete, StateAutocomplete
from oldp.utils.cache_per_user import cache_per_role

from . import views

app_name = "courts"
urlpatterns = [
    re_path(
        r"^$",
        cache_per_role(settings.CACHE_TTL)(views.CourtListView.as_view()),
        name="index",
    ),
    re_path(
        r"^state/(?P<state_slug>[-a-z0-9_]+)/$",
        cache_per_role(settings.CACHE_TTL)(views.CourtListView.as_view()),
        name="index_state",
    ),
    re_path(
        r"^autocomplete/state/$",
        cache_per_role(settings.CACHE_TTL)(StateAutocomplete.as_view()),
        name="state_autocomplete",
    ),
    re_path(
        r"^autocomplete/$",
        cache_per_role(settings.CACHE_TTL)(CourtAutocomplete.as_view()),
        name="autocomplete",
    ),
    re_path(
        r"^(?P<court_slug>[-a-z0-9_]+)/$",
        cache_per_role(settings.CACHE_TTL)(views.CourtCasesListView.as_view()),
        name="detail",
    ),
]
