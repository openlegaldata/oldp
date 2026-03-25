from django.urls import re_path

from . import stats_views, views

app_name = "cases"
urlpatterns = [
    re_path(r"^$", views.CaseFilterView.as_view(), name="index"),
    # Stats pages (before catch-all case_slug)
    re_path(r"^stats/$", stats_views.StatsOverviewView.as_view(), name="stats"),
    re_path(
        r"^stats/by_country/$",
        stats_views.StatsByCountryView.as_view(),
        name="stats_by_country",
    ),
    re_path(
        r"^stats/by_state/$",
        stats_views.StatsByStateView.as_view(),
        name="stats_by_state",
    ),
    re_path(
        r"^stats/by_court/$",
        stats_views.StatsByCourtView.as_view(),
        name="stats_by_court",
    ),
    re_path(
        r"^stats/by_source/$",
        stats_views.StatsBySourceView.as_view(),
        name="stats_by_source",
    ),
    # Case detail (catch-all, must be last)
    re_path(r"^(?P<case_slug>[-A-Za-z0-9_]+)$", views.case_view, name="case"),
]
