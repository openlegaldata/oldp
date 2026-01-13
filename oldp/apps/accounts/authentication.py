from django.utils.translation import gettext_lazy as _
from rest_framework import authentication, exceptions

from oldp.apps.accounts.models import APIToken


class APITokenAuthentication(authentication.TokenAuthentication):
    """
    Custom token authentication using the APIToken model.

    This authentication class extends DRF's TokenAuthentication to use our
    custom APIToken model with support for:
    - Multiple tokens per user
    - Token expiration
    - Active/inactive status
    - Usage tracking
    """

    model = APIToken
    keyword = "Token"

    def authenticate_credentials(self, key):
        """
        Authenticate the token and return the user and token.

        This method validates the token and checks for:
        - Token exists
        - Token is active
        - Token has not expired
        - Updates last_used timestamp
        """
        try:
            token = self.model.objects.select_related("user").get(key=key)
        except self.model.DoesNotExist:
            raise exceptions.AuthenticationFailed(_("Invalid token."))

        if not token.is_active:
            raise exceptions.AuthenticationFailed(_("Token is inactive."))

        if token.is_expired():
            raise exceptions.AuthenticationFailed(_("Token has expired."))

        if not token.user.is_active:
            raise exceptions.AuthenticationFailed(_("User inactive or deleted."))

        # Update last_used timestamp asynchronously to avoid performance impact
        token.mark_used()

        return (token.user, token)
