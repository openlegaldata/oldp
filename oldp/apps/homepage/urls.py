from django.conf import settings
from django.urls import re_path
from django.views.generic import TemplateView

from . import views

app_name = 'homepage'

urlpatterns = [
    re_path(r'^$', views.index_view, name='index'),
]

if settings.DEBUG:

    urlpatterns = [
            # Errors
            re_path(r'^error/400', views.error_bad_request_view),
            re_path(r'^error/403', views.error_permission_denied_view),
            re_path(r'^error/404', views.error404_view),
            re_path(r'^error/500', views.error500_view),
          ] + urlpatterns

