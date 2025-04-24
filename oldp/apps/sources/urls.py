from django.urls import re_path

from oldp.apps.sources import views

app_name = "sources"

urlpatterns = [
    re_path(r"^stats/$", views.stats_view, name="stats"),
]
