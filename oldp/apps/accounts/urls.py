from django.conf.urls import url

from oldp.apps.accounts import views

# app_name = 'accounts'

urlpatterns = [
    url(r'^profile/$', views.profile_view, name='account_profile'),
    url(r'^api/$', views.api_view, name='account_api'),
    url(r'^api/renew/$', views.api_renew_view, name='account_api_renew'),
]
