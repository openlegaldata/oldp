from django.conf.urls import url

from . import views

app_name = 'homepage'

urlpatterns = [
    # ex: /polls/
    url(r'^$', views.index, name='index'),
    url(r'^imprint$', views.imprint, name='imprint'),
    url(r'^privacy', views.privacy, name='privacy'),

    url(r'^help/api', views.api, name='help_api'),
    # url(r'^contact', views.contact, name='contact'),

]

