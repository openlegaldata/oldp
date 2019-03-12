from django.conf.urls import url

from . import views

app_name = 'contact'
urlpatterns = [
    url(r'^$', views.form_view, name='form'),
    url(r'^report_content$', views.report_content_view, name='report_content'),
    url(r'^thankyou', views.thankyou_view, name='thankyou'),
]

