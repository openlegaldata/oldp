from django.urls import re_path

from oldp.apps.accounts import views

# app_name = 'accounts'

urlpatterns = [
    re_path(r"^profile/$", views.profile_view, name="account_profile"),
    re_path(r"^profile/edit/$", views.profile_edit_view, name="account_profile_edit"),
    re_path(
        r"^profile/complete/$",
        views.profile_enrichment_view,
        name="account_profile_enrichment",
    ),
    re_path(
        r"^profile/newsletter/$",
        views.newsletter_preference_view,
        name="account_newsletter_preference",
    ),
    re_path(
        r"^newsletter/confirm/(?P<token>[^/]+)/$",
        views.newsletter_confirm_view,
        name="account_newsletter_confirm",
    ),
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
    # DSGVO/GDPR self-service
    re_path(r"^data-export/$", views.data_export_view, name="account_data_export"),
    re_path(r"^delete/$", views.account_delete_view, name="account_delete"),
]
