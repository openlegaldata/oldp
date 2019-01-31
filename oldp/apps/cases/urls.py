from django.conf.urls import url

from . import views

app_name = 'cases'
urlpatterns = [
    url(r'^$', views.CaseFilterView.as_view(), name='index'),
    url(r'^(?P<case_slug>[-A-Za-z0-9]+)$', views.case_view, name='case'),
]

