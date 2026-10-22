"""One email address per account.

An address is *taken* by another account when that account has it as its
``auth_user.email`` or as a **verified** allauth ``EmailAddress``. Unverified
secondary addresses of other accounts do not count: they are unproven claims,
and counting them would let anyone block an address by adding it to their own
account.

The checks here guard the entry points that allauth's signup check does not
cover (adding an address, confirming an address, the Django admin). The
database backs them up with case-insensitive unique indexes, see migration
``accounts.0015_unique_email_indexes``. Background and deployment notes:
``docs/bug-report-duplicate-emails.md``.
"""

from allauth.account.models import EmailAddress
from django.contrib.auth import get_user_model
from django.db.models import Count, Exists, OuterRef
from django.db.models.functions import Lower


def normalize_email(email):
    """Return ``email`` stripped and lowercased (``""`` for ``None``)."""
    return (email or "").strip().lower()


def is_email_taken(email, user=None):
    """Whether another account already holds ``email``.

    Args:
        email: Address to check (compared case-insensitively).
        user: The account that wants the address; its own rows are ignored.

    Returns:
        ``True`` if a different user has the address as ``User.email`` or as a
        verified ``EmailAddress``.
    """
    email = normalize_email(email)
    if not email:
        return False
    users = get_user_model().objects.filter(email__iexact=email)
    addresses = EmailAddress.objects.filter(email__iexact=email, verified=True)
    if user is not None and user.pk is not None:
        users = users.exclude(pk=user.pk)
        addresses = addresses.exclude(user_id=user.pk)
    return users.exists() or addresses.exists()


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
