from django.conf import settings
from django.conf.urls import url
from django.views.generic import TemplateView

from . import views

app_name = 'homepage'

urlpatterns = [
    url(r'^$', views.index_view, name='index'),
]

if settings.DEBUG:

    urlpatterns = [
            # Landing page
            url(r'^landing_page', TemplateView.as_view(template_name='homepage/landing_page.html')),

            # Errors
            url(r'^error/400', views.error_bad_request_view),
            url(r'^error/403', views.error_permission_denied_view),
            url(r'^error/404', views.error404_view),
            url(r'^error/500', views.error500_view),
          ] + urlpatterns

