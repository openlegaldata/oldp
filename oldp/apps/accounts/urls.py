from django.urls import re_path

from oldp.apps.accounts import views

# app_name = 'accounts'

urlpatterns = [
    re_path(r'^profile/$', views.profile_view, name='account_profile'),
    re_path(r'^api/$', views.api_view, name='account_api'),
    re_path(r'^api/renew/$', views.api_renew_view, name='account_api_renew'),
]
