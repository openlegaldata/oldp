"""One email address per account.

An address is *taken* by another account when that account has it as its
``auth_user.email`` or as a **verified** allauth ``EmailAddress``. Unverified
secondary addresses of other accounts do not count: they are unproven claims,
and counting them would let anyone block an address by adding it to their own
account.

Only an account that *holds* an address may use it: signup, adding and
confirming an address, the Django admin and password reset all apply this
rule (allauth's own checks count every ``EmailAddress`` row, so another
account's unconfirmed claim could block a signup or receive the password reset
link). The database backs them up with case-insensitive unique indexes, see migration
``accounts.0015_unique_email_indexes``. Background and deployment notes:
``docs/bug-report-duplicate-emails.md``.
"""

from allauth.account.models import EmailAddress
from django.contrib.auth import get_user_model
from django.db.models import Count, Exists, F, OuterRef, Q
from django.db.models.functions import Lower


def normalize_email(email):
    """Return ``email`` stripped and lowercased (``""`` for ``None``)."""
    return (email or "").strip().lower()


def holders_of_email(email):
    """Accounts that hold ``email``: as ``User.email`` or as a verified address.

    Args:
        email: Address to look up (compared case-insensitively).

    Returns:
        A ``User`` queryset (empty for a blank address).
    """
    email = normalize_email(email)
    User = get_user_model()
    if not email:
        return User.objects.none()
    verified = EmailAddress.objects.filter(
        user_id=OuterRef("pk"), email__iexact=email, verified=True
    )
    return User.objects.filter(Q(email__iexact=email) | Q(Exists(verified)))


def is_email_taken(email, user=None):
    """Whether another account already holds ``email``.

    Args:
        email: Address to check (compared case-insensitively).
        user: The account that wants the address; its own rows are ignored.

    Returns:
        ``True`` if a different user has the address as ``User.email`` or as a
        verified ``EmailAddress``.
    """
    holders = holders_of_email(email)
    if user is not None and user.pk is not None:
        holders = holders.exclude(pk=user.pk)
    return holders.exists()


def find_unverified_claims():
    """Unverified secondary addresses that another account holds.

    These rows are left over from before the add-email check. They can no
    longer be confirmed and are safe to delete.

    Returns:
        A list of ``EmailAddress`` rows, ordered by address and user id.
    """
    User = get_user_model()
    other_holder = User.objects.filter(
        Q(email__iexact=OuterRef("email"))
        | Q(
            Exists(
                EmailAddress.objects.filter(
                    user_id=OuterRef("pk"),
                    email__iexact=OuterRef(OuterRef("email")),
                    verified=True,
                )
            )
        )
    ).exclude(pk=OuterRef("user_id"))
    return list(
        EmailAddress.objects.filter(verified=False, primary=False)
        .filter(Exists(other_holder))
        # Not the account's own User.email: that case is a "cross" duplicate.
        .exclude(email__iexact=F("user__email"))
        .select_related("user")
        .order_by("email", "user_id")
    )


def find_duplicate_emails():
    """Find addresses that more than one account holds.

    Returns:
        A dict with three lists of lowercased addresses:

        * ``user_email``: shared by several ``auth_user.email`` values. Blocks
          the ``auth_user`` unique index.
        * ``verified_email_address``: verified ``EmailAddress`` on several
          accounts. Blocks the ``account_emailaddress`` unique index.
        * ``cross``: an account's ``auth_user.email`` is another account's
          verified ``EmailAddress``. No index covers this, but it is still a
          duplicate.
    """
    User = get_user_model()

    user_email = (
        User.objects.exclude(email="")
        .annotate(e=Lower("email"))
        .values("e")
        .annotate(n=Count("id"))
        .filter(n__gt=1)
        .values_list("e", flat=True)
    )
    verified = (
        EmailAddress.objects.filter(verified=True)
        .annotate(e=Lower("email"))
        .values("e")
        .annotate(n=Count("user_id", distinct=True))
        .filter(n__gt=1)
        .values_list("e", flat=True)
    )
    other_verified = EmailAddress.objects.filter(
        verified=True, email__iexact=OuterRef("email")
    ).exclude(user_id=OuterRef("pk"))
    cross = (
        User.objects.exclude(email="")
        .filter(Exists(other_verified))
        .annotate(e=Lower("email"))
        .values_list("e", flat=True)
        .distinct()
    )
    return {
        "user_email": sorted(user_email),
        "verified_email_address": sorted(verified),
        "cross": sorted(set(cross)),
    }


def accounts_for_email(email):
    """All accounts that hold ``email`` in any form, for reporting.

    Returns:
        A list of ``(user, addresses)`` tuples, ordered by user id, where
        ``addresses`` are that user's ``EmailAddress`` rows for the address.
    """
    email = normalize_email(email)
    User = get_user_model()
    user_ids = set(
        User.objects.filter(email__iexact=email).values_list("pk", flat=True)
    ) | set(
        EmailAddress.objects.filter(email__iexact=email).values_list(
            "user_id", flat=True
        )
    )
    result = []
    for user in User.objects.filter(pk__in=user_ids).order_by("pk"):
        addresses = list(EmailAddress.objects.filter(user=user, email__iexact=email))
        result.append((user, addresses))
    return result
