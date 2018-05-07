from django.conf.urls import url

from . import views

app_name = 'cases'
urlpatterns = [
    # ex: /polls/
    url(r'^$', views.index_view, name='index'),
    # url(r'^(?P<court_code>[-a-z0-9]+)/(?P<date>[-0-9]+)/(?P<file_number>[-a-z0-9]+)$', views.case, name='case'),
    url(r'^(?P<case_slug>[-A-Za-z0-9]+)$', views.case_view, name='case'),

    # ex: /polls/5/
]

