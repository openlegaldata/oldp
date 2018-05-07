from django.conf.urls import url

from . import views

app_name = 'contact'
urlpatterns = [
    # ex: /polls/
    url(r'^$', views.form, name='form'),
    url(r'^thankyou', views.thankyou, name='thankyou'),
    # url(r'^api', views.api, name='api'),
    # url(r'^contact', views.contact, name='contact'),

]

