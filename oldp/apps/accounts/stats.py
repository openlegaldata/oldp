"""Aggregate user statistics for a date range (``user_stats`` command).

Everything here is read-only and returns plain counts: no usernames, email
addresses or ids leave this module. The optional free-text export
(``free_text=True``) returns the profile text fields users typed in, stripped
of anything that identifies the account, for a qualitative read.

Definitions (see ``docs/user-stats.md``):

* **Signup** — a non-staff user whose ``date_joined`` falls in the range.
* **Activated** — the user has a verified email address (allauth
  ``EmailAddress.verified``). Password signups verify by clicking the
  confirmation link; social signups get a verified address when the provider
  vouches for it.
* **Funnel** — signups of the range, then how many of them verified, ever
  logged in, created an API token, used one, and connected an MCP client.
* **Login** — ``last_login`` falls in the range. OLDP keeps no login
  history, so a user who logged in during the range and again after it
  is missed; the count is a lower bound.

Never-verified signups are deleted by ``purge_unverified_users`` after a
grace period, so the activation ratio of older ranges looks better than it
was at the time.
"""

from collections import Counter
from datetime import datetime, time, timedelta

from allauth.account.models import EmailAddress
from allauth.socialaccount.models import SocialAccount
from django.contrib.auth import get_user_model
from django.db.models import Q
from django.db.models.functions import TruncMonth, TruncWeek
from django.utils import timezone

from oldp.apps.accounts.models import APIToken, UserProfile

User = get_user_model()

FREEMAIL_DOMAINS = {
    "aol.com",
    "freenet.de",
    "gmail.com",
    "gmx.at",
    "gmx.ch",
    "gmx.de",
    "gmx.net",
    "googlemail.com",
    "hotmail.com",
    "hotmail.de",
    "icloud.com",
    "live.com",
    "live.de",
    "mail.de",
    "mailbox.org",
    "me.com",
    "outlook.com",
    "outlook.de",
    "posteo.de",
    "proton.me",
    "protonmail.com",
    "t-online.de",
    "web.de",
    "yahoo.com",
    "yahoo.de",
}
# Domain labels that mark a German university address (``uni-koeln.de``,
# ``stud.tu-berlin.de``); ``.edu`` and ``.ac.<cc>`` are caught separately.
ACADEMIC_PREFIXES = ("uni-", "tu-", "fh-", "hs-", "th-", "hu-", "fu-")
TOP_N = 15
# Longer use-case texts are cut, the analysis needs the gist only.
FREE_TEXT_MAX_CHARS = 1000


def date_range(since, until):
    """Aware datetimes ``[start, end)`` covering the dates ``since``..``until``."""
    tz = timezone.get_current_timezone()
    start = timezone.make_aware(datetime.combine(since, time.min), tz)
    end = timezone.make_aware(datetime.combine(until + timedelta(days=1), time.min), tz)
    return start, end


def email_category(email):
    """``academic``, ``freemail``, ``other`` or ``none`` for an address."""
    domain = (email or "").rpartition("@")[2].strip().lower()
    if not domain:
        return "none"
    if domain in FREEMAIL_DOMAINS:
        return "freemail"
    labels = domain.split(".")
    if (
        "edu" in labels
        or "ac" in labels[:-1]
        or any(label.startswith(ACADEMIC_PREFIXES) for label in labels)
    ):
        return "academic"
    return "other"


def _ratio(part, whole):
    return round(part / whole, 4) if whole else None


def _top(counter, n=TOP_N):
    return [{"value": k, "count": v} for k, v in counter.most_common(n)]


def _users():
    """Everyone but the team: staff and superusers skew every ratio."""
    return User.objects.filter(is_staff=False, is_superuser=False)


def _in(field, start, end):
    """Filter kwargs for ``start <= field < end``."""
    return {f"{field}__gte": start, f"{field}__lt": end}


def _ids(qs, field="user_id"):
    return set(qs.values_list(field, flat=True))


def _oauth_user_ids(start=None, end=None):
    """Users with an MCP/OAuth grant or token, optionally created in a range.

    OAuth tokens expire and may be cleared, so this is a lower bound.
    """
    from oauth2_provider.models import (
        get_access_token_model,
        get_grant_model,
        get_refresh_token_model,
    )

    ids = set()
    for model in (
        get_grant_model(),
        get_access_token_model(),
        get_refresh_token_model(),
    ):
        qs = model.objects.filter(user__isnull=False)
        if start is not None:
            qs = qs.filter(created__gte=start, created__lt=end)
        ids |= _ids(qs)
    return ids


class _Lookups:
    """User-id sets shared by all period computations (one query each)."""

    def __init__(self):
        self.users = _ids(_users(), "pk")
        self.verified = _ids(EmailAddress.objects.filter(verified=True))
        self.social = dict(SocialAccount.objects.values_list("user_id", "provider"))
        self.with_token = _ids(APIToken.objects.all())
        self.token_used = _ids(APIToken.objects.filter(last_used__isnull=False))
        self.oauth = _oauth_user_ids()


def _period(start, end, lookups):
    """All range-scoped metrics for ``[start, end)``."""
    cohort = list(
        _users()
        .filter(**_in("date_joined", start, end))
        .select_related("profile")
        .only(
            "pk",
            "email",
            "last_login",
            "is_active",
            "profile__display_name",
            "profile__organization",
            "profile__role",
            "profile__use_case",
            "profile__country",
            "profile__newsletter_opt_in",
            "profile__newsletter_doi_confirmed_at",
        )
    )
    ids = {u.pk for u in cohort}
    signups = len(ids)

    methods = Counter(lookups.social.get(pk, "password") for pk in ids)
    verified = len(ids & lookups.verified)
    logged_in = sum(1 for u in cohort if u.last_login is not None)
    with_token = len(ids & lookups.with_token)
    token_used = len(ids & lookups.token_used)
    mcp = len(ids & lookups.oauth)

    profiles = [getattr(u, "profile", None) for u in cohort]
    profiles = [p for p in profiles if p is not None]
    filled = {
        field: sum(1 for p in profiles if (getattr(p, field) or "").strip())
        for field in ("display_name", "organization", "role", "use_case", "country")
    }
    complete = sum(1 for p in profiles if p.is_profile_complete)

    logins = _users().filter(**_in("last_login", start, end))
    login_count = logins.count()
    returning = logins.filter(date_joined__lt=start).count()

    profiles_all = UserProfile.objects.filter(
        user__is_staff=False, user__is_superuser=False
    )

    def profile_count(field):
        return profiles_all.filter(**_in(field, start, end)).count()

    optins = profiles_all.filter(**_in("newsletter_opt_in_at", start, end))
    subscribed = sum(1 for p in profiles if p.is_newsletter_subscriber)

    tokens = APIToken.objects.filter(user__is_staff=False, user__is_superuser=False)
    tokens_created = tokens.filter(**_in("created", start, end))
    tokens_used = tokens.filter(**_in("last_used", start, end))

    return {
        "signups": {
            "total": signups,
            "by_method": dict(methods.most_common()),
            "by_email_category": dict(
                Counter(email_category(u.email) for u in cohort).most_common()
            ),
            "inactive_accounts": sum(1 for u in cohort if not u.is_active),
        },
        "activation": {
            "activated": verified,
            "activation_ratio": _ratio(verified, signups),
        },
        "funnel": [
            {"step": "signed_up", "users": signups},
            {"step": "email_verified", "users": verified},
            {"step": "logged_in", "users": logged_in},
            {"step": "api_token_created", "users": with_token},
            {"step": "api_token_used", "users": token_used},
            {"step": "mcp_connected", "users": mcp},
        ],
        "logins": {
            "users_last_login_in_range": login_count,
            "returning_users": returning,
            "new_users": login_count - returning,
        },
        "newsletter": {
            "opt_ins_requested": optins.count(),
            "opt_ins_by_source": dict(
                Counter(optins.values_list("consent_source", flat=True)).most_common()
            ),
            "double_opt_ins_confirmed": profile_count("newsletter_doi_confirmed_at"),
            "signups_subscribed": subscribed,
            "signups_subscribed_ratio": _ratio(subscribed, signups),
        },
        "profile": {
            "signups_complete": complete,
            "signups_complete_ratio": _ratio(complete, signups),
            "signups_field_fill": {
                field: {"users": n, "ratio": _ratio(n, signups)}
                for field, n in filled.items()
            },
            "signups_by_role": dict(
                Counter(p.role or "(empty)" for p in profiles).most_common()
            ),
            "signups_by_country": _top(
                Counter(p.country or "(empty)" for p in profiles)
            ),
            "enrichment_prompts_shown": profile_count("enrichment_prompted_at"),
            "profiles_enriched": profile_count("enriched_at"),
        },
        "api": {
            "tokens_created": tokens_created.count(),
            "users_creating_tokens": tokens_created.values("user").distinct().count(),
            "tokens_used": tokens_used.count(),
            "users_using_tokens": tokens_used.values("user").distinct().count(),
            "users_connecting_mcp": len(_oauth_user_ids(start, end) & lookups.users),
        },
        "lifecycle": {
            "inactivity_warnings_sent": profile_count("deletion_warning_sent_at"),
            "deactivated": profile_count("deactivated_at"),
            "anonymized": profile_count("anonymized_at"),
        },
    }


def _cohorts(start, end, lookups, trunc, key):
    """Signups per week/month with how far each bucket got down the funnel."""
    joined = _users().filter(**_in("date_joined", start, end))
    buckets = {}
    for bucket, pk in joined.annotate(bucket=trunc("date_joined")).values_list(
        "bucket", "pk"
    ):
        buckets.setdefault(bucket.date().isoformat(), set()).add(pk)
    logged_in = _ids(joined.filter(last_login__isnull=False), "pk")
    rows = []
    for label in sorted(buckets):
        ids = buckets[label]
        n = len(ids)
        rows.append(
            {
                key: label,
                "signups": n,
                "verified": len(ids & lookups.verified),
                "verified_ratio": _ratio(len(ids & lookups.verified), n),
                "logged_in_ratio": _ratio(len(ids & logged_in), n),
                "api_token_ratio": _ratio(len(ids & lookups.with_token), n),
            }
        )
    return rows


def _totals(lookups):
    users = _users()
    ids = lookups.users
    profiles = UserProfile.objects.filter(user__in=users)
    subscribers = profiles.filter(
        newsletter_opt_in=True, newsletter_doi_confirmed_at__isnull=False
    ).count()
    complete = sum(
        1 for p in profiles.only("role", "use_case") if p.is_profile_complete
    )
    return {
        "users": len(ids),
        "active_accounts": users.filter(is_active=True).count(),
        "verified": len(ids & lookups.verified),
        "social_login": len(ids & set(lookups.social)),
        "newsletter_subscribers": subscribers,
        "newsletter_pending_confirmation": profiles.filter(
            newsletter_opt_in=True, newsletter_doi_confirmed_at__isnull=True
        ).count(),
        "complete_profiles": complete,
        "with_api_token": len(ids & lookups.with_token),
        "mcp_connected": len(ids & lookups.oauth),
        "never_logged_in": users.filter(last_login__isnull=True).count(),
    }


def free_text(start, end):
    """Profile free text of users who signed up or enriched in the range.

    Only the text and the coarse role/country/email category are returned —
    nothing that identifies the account.
    """
    profiles = (
        UserProfile.objects.filter(user__is_staff=False, user__is_superuser=False)
        .filter(
            Q(**_in("user__date_joined", start, end))
            | Q(**_in("enriched_at", start, end))
        )
        .select_related("user")
        .order_by("user__date_joined")
    )
    rows = []
    for p in profiles:
        text = {
            "display_name": p.display_name.strip(),
            "organization": p.organization.strip(),
            "use_case": p.use_case.strip()[:FREE_TEXT_MAX_CHARS],
        }
        if not any(text.values()):
            continue
        rows.append(
            {
                **text,
                "role": p.role,
                "country": p.country,
                "email_category": email_category(p.user.email),
                "joined_in_range": start <= p.user.date_joined < end,
            }
        )
    return rows


def user_stats(since, until, include_free_text=False):
    """The full report for the dates ``since``..``until`` (inclusive).

    ``previous`` covers the equally long range right before, for trends.
    """
    start, end = date_range(since, until)
    prev_start, prev_end = start - (end - start), start
    lookups = _Lookups()

    report = {
        "range": {
            "since": since.isoformat(),
            "until": until.isoformat(),
            "previous_since": prev_start.date().isoformat(),
            "previous_until": (prev_end - timedelta(days=1)).date().isoformat(),
        },
        "generated_at": timezone.now().isoformat(timespec="seconds"),
        "totals": _totals(lookups),
        "current": _period(start, end, lookups),
        "previous": _period(prev_start, prev_end, lookups),
        "weekly_signups": _cohorts(start, end, lookups, TruncWeek, "week"),
        "monthly_cohorts": _cohorts(start, end, lookups, TruncMonth, "month"),
    }
    if include_free_text:
        report["free_text"] = free_text(start, end)
    return report
