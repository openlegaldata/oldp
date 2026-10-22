import logging
import smtplib
from urllib.parse import urlencode

from allauth.account.adapter import DefaultAccountAdapter
from allauth.core import context as allauth_context
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from django.contrib import messages
from django.urls import reverse
from django.utils.translation import gettext as _

from oldp.apps.accounts.email_uniqueness import is_email_taken

logger = logging.getLogger(__name__)

# Set on the request when sending an email failed.
EMAIL_SEND_FAILED_ATTR = "oldp_email_send_failed"
# Query parameter for the verification-sent page, see
# templates/account/verification_sent.html.
SEND_FAILED_PARAM = "send_failed"
CONFIRMATION_SENT_MESSAGE = "account/messages/email_confirmation_sent.txt"


class CustomAccountAdapter(DefaultAccountAdapter):
    """Custom account adapter that gracefully handles email sending errors."""

    def get_login_redirect_url(self, request):
        """Send users with an incomplete profile to the one-time enrichment prompt.

        This only sets the *default* post-login destination. allauth still
        honours an explicit ``next`` first, so the MCP/OAuth authorize flow is
        unaffected — only a plain web login is redirected, and only once (the
        prompt records that it was shown).
        """
        default_url = super().get_login_redirect_url(request)
        user = getattr(request, "user", None)
        profile = getattr(user, "profile", None) if user else None
        if profile is not None and profile.is_enrichment_needed:
            return reverse("account_profile_enrichment")
        return default_url

    def confirm_email(self, request, email_address):
        """Refuse to confirm an address that another account already holds.

        Confirming makes the address verified and, if the user has no primary
        address yet, copies it into ``User.email``. Both would duplicate
        another account's address (and hit the unique indexes).
        """
        if is_email_taken(email_address.email, email_address.user):
            logger.warning(
                "Refused to confirm %s for user %s: taken by another account",
                email_address.email,
                email_address.user_id,
            )
            self.add_message(
                request,
                messages.ERROR,
                "account/messages/email_confirmation_failed.txt",
                {"email": email_address.email},
            )
            return False
        return super().confirm_email(request, email_address)

    def send_mail(self, template_prefix, email, context):
        """Send email with error handling for SMTP failures.

        A failed send is logged and reported to the user, and the request is
        marked so that allauth's "Confirmation email sent" message and page
        do not claim otherwise (see ``add_message`` and
        ``respond_email_verification_sent``).
        """
        try:
            return super().send_mail(template_prefix, email, context)
        except smtplib.SMTPDataError as e:
            # SMTP server rejected the message (e.g., spam filter)
            smtp_error = (
                e.smtp_error.decode()
                if isinstance(e.smtp_error, bytes)
                else e.smtp_error
            )
            return self._send_failed(
                f"SMTP server rejected email to {email}: {e.smtp_code} {smtp_error}",
                _(
                    "Unable to send verification email. Please contact support "
                    "if this issue persists."
                ),
            )
        except (
            smtplib.SMTPException,
            ConnectionRefusedError,
            TimeoutError,
            OSError,
        ) as e:
            # Other email sending errors (connection issues, etc.)
            return self._send_failed(
                f"Failed to send email to {email}: {type(e).__name__}: {str(e)}",
                _("Email service is temporarily unavailable. Please try again later."),
            )
        except Exception as e:
            # Catch any other unexpected errors
            return self._send_failed(
                f"Unexpected error sending email to {email}: {type(e).__name__}: {str(e)}",
                _("An error occurred while sending email. Please contact support."),
            )

    def _send_failed(self, log_message, user_message):
        """Log a failed send and tell the user (when there is a request)."""
        logger.error(log_message, exc_info=True)
        # allauth's mail context does not carry the request; its request
        # context does (set by allauth's AccountMiddleware).
        request = allauth_context.request
        if request is not None:
            setattr(request, EMAIL_SEND_FAILED_ATTR, True)
            messages.error(request, user_message)
        return False

    def add_message(
        self,
        request,
        level,
        message_template=None,
        message_context=None,
        extra_tags="",
        message=None,
    ):
        """Drop allauth's "Confirmation email sent" message if sending failed."""
        if message_template == CONFIRMATION_SENT_MESSAGE and getattr(
            request, EMAIL_SEND_FAILED_ATTR, False
        ):
            return
        super().add_message(
            request,
            level,
            message_template=message_template,
            message_context=message_context,
            extra_tags=extra_tags,
            message=message,
        )

    def respond_email_verification_sent(self, request, user):
        """Show the "could not send" variant of the page if sending failed."""
        response = super().respond_email_verification_sent(request, user)
        if getattr(request, EMAIL_SEND_FAILED_ATTR, False) and response.has_header(
            "Location"
        ):
            response["Location"] += "?" + urlencode({SEND_FAILED_PARAM: 1})
        return response


class CustomSocialAccountAdapter(DefaultSocialAccountAdapter):
    """Map social-provider profile data onto the user's UserProfile.

    Runs for GitHub/Google sign-ups. The profile row is created by the
    post_save signal when the user is saved; here we prefill the display name
    and (for GitHub) the organization/company from the provider's extra data.
    """

    def save_user(self, request, sociallogin, form=None):
        user = super().save_user(request, sociallogin, form=form)

        profile = getattr(user, "profile", None)
        if profile is None:
            return user

        extra = sociallogin.account.extra_data or {}
        updated_fields = []

        if not profile.display_name:
            display_name = extra.get("name") or user.get_full_name()
            if display_name:
                profile.display_name = display_name[:150]
                updated_fields.append("display_name")

        # GitHub exposes "company"; Google does not.
        if not profile.organization and extra.get("company"):
            profile.organization = str(extra["company"])[:200]
            updated_fields.append("organization")

        if updated_fields:
            profile.save(update_fields=updated_fields + ["updated"])

        return user
