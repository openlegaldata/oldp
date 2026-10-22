"""Case-insensitive unique indexes on user email addresses.

Two rules are enforced in the database:

* ``auth_user``: no two accounts share an email address. Blank addresses are
  exempt, because anonymized accounts get ``email = ""``.
* ``account_emailaddress``: no two **verified** allauth addresses are equal.
  This is what allauth's own ``unique_verified_email`` constraint is meant to
  do, but Django skips that constraint on MySQL/MariaDB (no partial index
  support, ``models.W036``), so production had no unique index at all.

How it is implemented per backend:

* MySQL/MariaDB has neither partial nor functional indexes (MariaDB), so a
  hidden stored generated column holds the lowercased address, or ``NULL``
  when the row is exempt, and carries a ``UNIQUE`` key (``NULL`` values never
  collide). The columns are ``auth_user.oldp_email_ci`` and
  ``account_emailaddress.oldp_verified_email_ci``. Django does not know about
  them and never selects or writes them.
* SQLite and PostgreSQL get partial unique indexes on ``LOWER(email)``.
* Other backends are skipped with a log message.

The migration refuses to run while duplicates exist and names the command
that lists them (``manage.py find_duplicate_emails``). See
``docs/bug-report-duplicate-emails.md`` for the deployment steps.
"""

from __future__ import annotations

import logging

from django.db import migrations
from django.db.models import Count
from django.db.models.functions import Lower

logger = logging.getLogger(__name__)

USER_INDEX = "auth_user_email_ci_uniq"
USER_COLUMN = "oldp_email_ci"
ADDRESS_INDEX = "account_emailaddress_verified_email_ci_uniq"
ADDRESS_COLUMN = "oldp_verified_email_ci"

MYSQL_FORWARD = [
    f"ALTER TABLE auth_user"
    f" ADD COLUMN {USER_COLUMN} VARCHAR(254)"
    f" AS (NULLIF(LOWER(email), '')) STORED,"
    f" ADD UNIQUE KEY {USER_INDEX} ({USER_COLUMN})",
    f"ALTER TABLE account_emailaddress"
    f" ADD COLUMN {ADDRESS_COLUMN} VARCHAR(254)"
    f" AS (IF(verified, LOWER(email), NULL)) STORED,"
    f" ADD UNIQUE KEY {ADDRESS_INDEX} ({ADDRESS_COLUMN})",
]
MYSQL_REVERSE = [
    f"ALTER TABLE auth_user DROP INDEX {USER_INDEX}, DROP COLUMN {USER_COLUMN}",
    f"ALTER TABLE account_emailaddress"
    f" DROP INDEX {ADDRESS_INDEX}, DROP COLUMN {ADDRESS_COLUMN}",
]
PARTIAL_FORWARD = [
    f"CREATE UNIQUE INDEX {USER_INDEX} ON auth_user (LOWER(email)) WHERE email <> ''",
    f"CREATE UNIQUE INDEX {ADDRESS_INDEX} ON account_emailaddress (LOWER(email))"
    f" WHERE verified",
]
PARTIAL_REVERSE = [
    f"DROP INDEX IF EXISTS {USER_INDEX}",
    f"DROP INDEX IF EXISTS {ADDRESS_INDEX}",
]


def _statements(vendor, forward):
    if vendor == "mysql":
        return MYSQL_FORWARD if forward else MYSQL_REVERSE
    if vendor in ("sqlite", "postgresql"):
        return PARTIAL_FORWARD if forward else PARTIAL_REVERSE
    return None


def _check_no_duplicates(apps, db_alias):
    User = apps.get_model("auth", "User")
    EmailAddress = apps.get_model("account", "EmailAddress")

    user_dupes = (
        User.objects.using(db_alias)
        .exclude(email="")
        .annotate(e=Lower("email"))
        .values("e")
        .annotate(n=Count("id"))
        .filter(n__gt=1)
        .count()
    )
    address_dupes = (
        EmailAddress.objects.using(db_alias)
        .filter(verified=True)
        .annotate(e=Lower("email"))
        .values("e")
        .annotate(n=Count("user_id", distinct=True))
        .filter(n__gt=1)
        .count()
    )
    if user_dupes or address_dupes:
        raise RuntimeError(
            f"Cannot add unique email indexes: {user_dupes} address(es) are "
            f"shared by several auth_user rows and {address_dupes} verified "
            f"address(es) by several accounts. Run "
            f"'manage.py find_duplicate_emails', resolve them and migrate "
            f"again (see docs/bug-report-duplicate-emails.md)."
        )


def forwards(apps, schema_editor):
    vendor = schema_editor.connection.vendor
    statements = _statements(vendor, forward=True)
    if statements is None:
        logger.warning("No unique email indexes for database vendor %r", vendor)
        return
    _check_no_duplicates(apps, schema_editor.connection.alias)
    for sql in statements:
        schema_editor.execute(sql)


def backwards(apps, schema_editor):
    statements = _statements(schema_editor.connection.vendor, forward=False)
    for sql in statements or []:
        schema_editor.execute(sql)


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0014_newsletter_consent_text_data"),
        ("auth", "0012_alter_user_first_name_max_length"),
        # 0006 lowercases all stored addresses; run after it.
        ("account", "0006_emailaddress_lower"),
    ]

    # MySQL cannot roll back DDL, and Django refuses DDL inside a transaction
    # there. SQLite/PostgreSQL still run this inside the migration transaction.
    operations = [migrations.RunPython(forwards, backwards, atomic=False)]
