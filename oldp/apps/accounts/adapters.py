import logging
import smtplib

from allauth.account.adapter import DefaultAccountAdapter
from django.contrib import messages

logger = logging.getLogger(__name__)


class CustomAccountAdapter(DefaultAccountAdapter):
    """Custom account adapter that gracefully handles email sending errors."""

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
