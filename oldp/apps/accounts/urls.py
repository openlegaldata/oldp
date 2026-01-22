from django.urls import re_path

from oldp.apps.accounts import views

# app_name = 'accounts'

urlpatterns = [
    re_path(r"^profile/$", views.profile_view, name="account_profile"),
    re_path(r"^api/$", views.api_view, name="account_api"),
    re_path(r"^api/renew/$", views.api_renew_view, name="account_api_renew"),
    # Multi-token system URLs
    re_path(r"^api/tokens/$", views.api_tokens_list_view, name="account_api_tokens"),
    re_path(
        r"^api/tokens/create/$",
        views.api_token_create_view,
        name="account_api_token_create",
    ),
    re_path(
        r"^api/tokens/(?P<token_id>\d+)/revoke/$",
        views.api_token_revoke_view,
        name="account_api_token_revoke",
    ),
]
