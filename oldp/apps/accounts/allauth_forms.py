"""Overrides of allauth's built-in forms, wired via ``ACCOUNT_FORMS``.

Kept apart from ``oldp.apps.accounts.forms``: allauth imports that module
(``ACCOUNT_SIGNUP_FORM_CLASS``) while ``allauth.account.forms`` is still
loading, so importing allauth's forms there would be circular.
"""

from allauth.account.adapter import get_adapter
from allauth.account.forms import AddEmailForm

from oldp.apps.accounts.email_uniqueness import is_email_taken, normalize_email


class UniqueAddEmailForm(AddEmailForm):
    """Add-email form that refuses addresses held by another account.

    allauth accepts such an address silently when enumeration prevention is
    on, which let a second account take over an address that the first
    account never confirmed. Here the user is logged in, so telling them the
    address is taken reveals little; the ``manage_email`` rate limit applies.
    """

    def clean_email(self):
        email = normalize_email(self.cleaned_data.get("email"))
        if is_email_taken(email, self.user):
            raise get_adapter().validation_error("email_taken")
        return super().clean_email()
