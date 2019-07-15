from django.conf.urls import url

from oldp.apps.sources import views

app_name = 'sources'

urlpatterns = [
    url(r'^stats/$', views.stats_view, name='stats'),
]
