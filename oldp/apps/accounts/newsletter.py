"""Newsletter double-opt-in (DOI) helpers.

German law (UWG §7 / DSGVO) requires *proof* of consent for marketing email,
which courts interpret as double-opt-in: the user opts in on-site, then confirms
via a link emailed to them. Only after confirmation may marketing mail be sent.

This module only handles *capturing and confirming* consent. It does NOT send
any bulk/marketing mail — that machinery is intentionally out of scope (see the
oldp-user-v2 runbook). The single confirmation email here is transactional.
"""

import logging

from django.conf import settings
from django.core import signing
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.urls import reverse

logger = logging.getLogger(__name__)

# Namespacing salt + how long a confirmation link stays valid.
DOI_SALT = "accounts.newsletter.doi"
DOI_MAX_AGE_SECONDS = 7 * 24 * 60 * 60  # 7 days


def make_doi_token(user):
    """Return a signed, expiring token that identifies the user."""
    return signing.dumps(user.pk, salt=DOI_SALT)


def read_doi_token(token):
    """Return the user pk for a valid token, or ``None`` if invalid/expired."""
    try:
        return signing.loads(token, salt=DOI_SALT, max_age=DOI_MAX_AGE_SECONDS)
    except signing.BadSignature:
        return None


def start_double_opt_in(request, profile):
    """Send the double-opt-in confirmation email for a pending opt-in.

    Safe to call whenever ``profile.newsletter_opt_in`` is set but not yet
    confirmed. Failures are logged and swallowed so a mail outage never breaks
    signup or the dashboard save.
    """
    user = profile.user
    if not user.email:
        logger.warning("Cannot send DOI email to user %s: no email address", user.pk)
        return

    token = make_doi_token(user)
    confirm_path = reverse("account_newsletter_confirm", kwargs={"token": token})
    confirm_url = request.build_absolute_uri(confirm_path)

    context = {"user": user, "confirm_url": confirm_url}
    subject = render_to_string(
        "accounts/email/newsletter_confirm_subject.txt", context
    ).strip()
    body = render_to_string("accounts/email/newsletter_confirm_message.txt", context)

    try:
        send_mail(
            subject,
            body,
            settings.DEFAULT_FROM_EMAIL,
            [user.email],
            fail_silently=False,
        )
    except Exception as e:  # noqa: BLE001 — never let mail break the flow
        logger.error(
            "Failed to send newsletter DOI email to %s: %s: %s",
            user.email,
            type(e).__name__,
            e,
            exc_info=True,
        )
