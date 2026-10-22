"""Overrides of allauth's built-in forms, wired via ``ACCOUNT_FORMS``.

Kept apart from ``oldp.apps.accounts.forms``: allauth imports that module
(``ACCOUNT_SIGNUP_FORM_CLASS``) while ``allauth.account.forms`` is still
loading, so importing allauth's forms there would be circular.
"""

from allauth.account.adapter import get_adapter
from allauth.account.forms import AddEmailForm, ResetPasswordForm, SignupForm

from oldp.apps.accounts.email_uniqueness import (
    holders_of_email,
    is_email_taken,
    normalize_email,
)


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


class UniqueSignupForm(SignupForm):
    """Signup form that ignores other accounts' unconfirmed claims.

    allauth treats an address as existing if any account has it, even as an
    unverified secondary address. The real owner of such an address then gets
    an "Account Already Exists" mail instead of a confirmation, and cannot sign
    up. Here only accounts that hold the address count; for those allauth's
    behaviour (no account, "Account Already Exists" mail) is kept.
    """

    def validate_unique_email(self, value):
        if is_email_taken(value):
            return super().validate_unique_email(value)
        self.account_already_exists = False
        return get_adapter().validate_unique_email(value)


class HolderOnlyResetPasswordForm(ResetPasswordForm):
    """Password reset that only mails links for accounts holding the address.

    allauth also includes accounts that merely added the address without
    confirming it, so whoever controls the mailbox could reset the password of
    an account that is not theirs.
    """

    def clean_email(self):
        email = super().clean_email()
        holder_ids = set(holders_of_email(email).values_list("pk", flat=True))
        self.users = [user for user in self.users if user.pk in holder_ids]
        return email
