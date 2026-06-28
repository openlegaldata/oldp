import logging
import smtplib

from allauth.account.adapter import DefaultAccountAdapter
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from django.contrib import messages
from django.urls import reverse

logger = logging.getLogger(__name__)


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

    def send_mail(self, template_prefix, email, context):
        """Send email with error handling for SMTP failures."""
        try:
            return super().send_mail(template_prefix, email, context)
        except smtplib.SMTPDataError as e:
            # SMTP server rejected the message (e.g., spam filter)
            logger.error(
                f"SMTP server rejected email to {email}: {e.smtp_code} {e.smtp_error.decode() if isinstance(e.smtp_error, bytes) else e.smtp_error}",
                exc_info=True,
            )
            # Get request from context if available to show user message
            request = context.get("request")
            if request:
                messages.error(
                    request,
                    "Unable to send verification email. Please contact support if this issue persists.",
                )
            return False
        except (
            smtplib.SMTPException,
            ConnectionRefusedError,
            TimeoutError,
            OSError,
        ) as e:
            # Other email sending errors (connection issues, etc.)
            logger.error(
                f"Failed to send email to {email}: {type(e).__name__}: {str(e)}",
                exc_info=True,
            )
            request = context.get("request")
            if request:
                messages.error(
                    request,
                    "Email service is temporarily unavailable. Please try again later.",
                )
            return False
        except Exception as e:
            # Catch any other unexpected errors
            logger.error(
                f"Unexpected error sending email to {email}: {type(e).__name__}: {str(e)}",
                exc_info=True,
            )
            request = context.get("request")
            if request:
                messages.error(
                    request,
                    "An error occurred while sending email. Please contact support.",
                )
            return False


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
