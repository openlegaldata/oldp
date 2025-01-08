from django.urls import re_path

from . import views

app_name = 'cases'
urlpatterns = [
    re_path(r'^$', views.CaseFilterView.as_view(), name='index'),
    re_path(r'^(?P<case_slug>[-A-Za-z0-9]+)$', views.case_view, name='case'),
]

