"""Inactive-account lifecycle: detection, warning, deactivation, anonymization.

These helpers back the manual ``warn_inactive_users`` and
``purge_inactive_users`` management commands. **Nothing here runs
automatically** — an operator runs the commands by hand (see the deployment
README).

The flow (all timings configurable via settings / env):

    dormant --warn--> warned --grace--> deactivated --grace--> anonymized

* **dormant** — no login *and* no API-token use for
  ``INACTIVE_USER_DORMANCY_DAYS``.
* **warned** — a one-off, strictly administrative service email asks the user
  to log in by a deadline. Logging in clears the warning (see
  ``accounts.signals``), which is what makes that promise true.
* **deactivated** — ``is_active=False`` after the warning grace passes with no
  login. Reversible by an admin.
* **anonymized** — after a further grace, personal data is scrubbed and tokens
  disabled. Token-created **content is kept**: ``created_by_token`` is
  ``SET_NULL`` on delete and we only *deactivate* tokens, so cases/laws/courts
  survive — they merely lose user attribution.

Excluded from the whole flow: staff/superusers and "power"/paying users (any
custom token ``rate_limit``, any custom ``max_api_tokens``, or recent token
use). Only accounts with a *verified* email are ever warned/scrubbed here;
never-verified signups are a separate concern.

Service-email note (UWG §7): the warning is transactional/administrative and
needs no marketing consent — keep it free of any promotional content.
"""

import logging
from datetime import timedelta

from allauth.account.models import EmailAddress
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.mail import send_mail
from django.db import transaction
from django.db.models import Q
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone

from oldp.apps.accounts.models import APIToken

logger = logging.getLogger(__name__)

User = get_user_model()


# --- Time windows --------------------------------------------------------


def dormancy_cutoff(now=None):
    """Datetime before which last activity counts as dormant."""
    now = now or timezone.now()
    return now - timedelta(days=settings.INACTIVE_USER_DORMANCY_DAYS)


def warning_deadline(now=None):
    """Deadline shown in the warning email (now + warning grace)."""
    now = now or timezone.now()
    return now + timedelta(days=settings.INACTIVE_USER_WARNING_GRACE_DAYS)


# --- Population queries ---------------------------------------------------


def eligible_inactive_users(cutoff=None):
    """Active, dormant, non-exempt users — the population the flow may touch.

    A user is included when they are active, not staff, have a verified email,
    have not logged in (nor used an API token) since ``cutoff``, and are not a
    power/paying user.
    """
    cutoff = cutoff or dormancy_cutoff()

    # Recent API activity => not dormant.
    recent_token_user_ids = APIToken.objects.filter(last_used__gte=cutoff).values_list(
        "user_id", flat=True
    )
    # Power/paying users: a custom per-token rate limit.
    paying_user_ids = APIToken.objects.filter(rate_limit__isnull=False).values_list(
        "user_id", flat=True
    )
    # Only ever touch accounts whose email was actually confirmed.
    verified_user_ids = EmailAddress.objects.filter(verified=True).values_list(
        "user_id", flat=True
    )

    return (
        User.objects.filter(is_active=True, is_staff=False, is_superuser=False)
        .filter(
            Q(last_login__lt=cutoff)
            | Q(last_login__isnull=True, date_joined__lt=cutoff)
        )
        .filter(pk__in=verified_user_ids)
        .exclude(pk__in=recent_token_user_ids)
        .exclude(pk__in=paying_user_ids)
        .exclude(profile__max_api_tokens__isnull=False)
        .select_related("profile")
    )


def users_to_warn(cutoff=None):
    """Dormant, eligible users who have not been warned yet."""
    return eligible_inactive_users(cutoff).filter(
        profile__deletion_warning_sent_at__isnull=True,
        profile__anonymized_at__isnull=True,
    )


def users_to_deactivate(now=None):
    """Warned users past their deadline who never logged back in.

    Logging in clears ``deletion_scheduled_for``, so a non-null value in the
    past means the user ignored the warning. Staff/superusers are re-excluded
    defensively in case a role changed after the warning was issued.
    """
    now = now or timezone.now()
    return (
        User.objects.filter(is_active=True, is_staff=False, is_superuser=False)
        .filter(
            profile__deletion_scheduled_for__isnull=False,
            profile__deletion_scheduled_for__lte=now,
            profile__deactivated_at__isnull=True,
        )
        .select_related("profile")
    )


def users_to_anonymize(now=None):
    """Deactivated users whose deactivation grace has elapsed."""
    now = now or timezone.now()
    deadline = now - timedelta(days=settings.INACTIVE_USER_DEACTIVATION_GRACE_DAYS)
    return (
        User.objects.filter(is_active=False)
        .filter(
            profile__deactivated_at__isnull=False,
            profile__deactivated_at__lte=deadline,
            profile__anonymized_at__isnull=True,
        )
        .select_related("profile")
    )


# --- Email ----------------------------------------------------------------


def _absolute_url(path):
    return settings.SITE_URL.rstrip("/") + path


def render_warning_email(user, deadline):
    """Return ``(subject, body)`` for the bilingual inactivity warning."""
    context = {
        "user": user,
        "deadline": deadline,
        "login_url": _absolute_url(reverse("account_login")),
        "reset_url": _absolute_url(reverse("account_reset_password")),
        "contact_url": _absolute_url(reverse("contact:form")),
        # User-facing brand name (SITE_NAME is the internal short "OLDP").
        "site_name": settings.SITE_TITLE,
        "site_url": settings.SITE_URL,
    }
    subject = render_to_string(
        "accounts/email/inactive_warning_subject.txt", context
    ).strip()
    body = render_to_string("accounts/email/inactive_warning_message.txt", context)
    return subject, body


def send_warning_email(user, deadline):
    """Send the warning email. Returns ``True`` on success."""
    if not user.email:
        logger.warning("Cannot warn user %s: no email address", user.pk)
        return False
    subject, body = render_warning_email(user, deadline)
    try:
        send_mail(
            subject,
            body,
            settings.DEFAULT_FROM_EMAIL,
            [user.email],
            fail_silently=False,
        )
        return True
    except Exception as e:  # noqa: BLE001 — one bad address must not stop the run
        logger.error(
            "Failed to send inactivity warning to %s: %s: %s",
            user.email,
            type(e).__name__,
            e,
            exc_info=True,
        )
        return False


def mark_warned(profile, deadline, now=None):
    """Record that the warning was sent and when deletion is scheduled."""
    now = now or timezone.now()
    profile.deletion_warning_sent_at = now
    profile.deletion_scheduled_for = deadline
    profile.save(
        update_fields=["deletion_warning_sent_at", "deletion_scheduled_for", "updated"]
    )


# --- State transitions ----------------------------------------------------


@transaction.atomic
def deactivate_user(user, now=None):
    """Set ``is_active=False`` and stamp ``deactivated_at`` (reversible)."""
    now = now or timezone.now()
    profile = user.profile
    user.is_active = False
    user.save(update_fields=["is_active"])
    profile.deactivated_at = now
    profile.save(update_fields=["deactivated_at", "updated"])


@transaction.atomic
def anonymize_user(user, now=None):
    """Scrub personal data while keeping the row and token-created content.

    - User: username -> ``deleted_<pk>``, blank email/names, unusable
      password, stays ``is_active=False``.
    - allauth ``EmailAddress`` + ``SocialAccount`` rows: deleted (they carry
      email/identity).
    - Legacy DRF ``Token``: deleted (kills API access).
    - ``APIToken`` rows: deactivated but **kept**, so ``created_by_token``
      attribution chains stay intact; keys are random, not personal data.
    - Profile: clear free-text/contact fields + newsletter consent; stamp
      ``anonymized_at``.
    """
    from allauth.socialaccount.models import SocialAccount
    from rest_framework.authtoken.models import Token

    now = now or timezone.now()
    profile = user.profile

    EmailAddress.objects.filter(user=user).delete()
    SocialAccount.objects.filter(user=user).delete()
    Token.objects.filter(user=user).delete()
    APIToken.objects.filter(user=user).update(is_active=False)

    user.username = f"deleted_{user.pk}"
    user.email = ""
    user.first_name = ""
    user.last_name = ""
    user.is_active = False
    user.set_unusable_password()
    user.save()

    profile.display_name = ""
    profile.organization = ""
    profile.role = ""
    profile.use_case = ""
    profile.country = ""
    profile.newsletter_opt_in = False
    profile.newsletter_opt_in_at = None
    profile.newsletter_doi_confirmed_at = None
    profile.consent_source = ""
    profile.anonymized_at = now
    profile.save()
