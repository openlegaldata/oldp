"""Convert auth-related tables to ``utf8mb4`` on MySQL/MariaDB.

Production runs MariaDB with a connection charset of ``utf8mb4`` and
collation ``utf8mb4_uca1400_ai_ci`` (the MariaDB 11 default), but the
``auth_*``, ``account_*``, ``socialaccount_*``, ``django_session`` and
``authtoken_*`` tables were originally created when the server default
was ``latin1_swedish_ci`` and never converted.

Result: every ``WHERE email = %s`` / ``WHERE username = %s`` query in the
login flow compares a ``latin1_swedish_ci`` column against a
``utf8mb4_*`` string literal and MariaDB refuses with::

    OperationalError (1267, "Illegal mix of collations
    (latin1_swedish_ci,IMPLICIT) and (utf8mb4_uca1400_ai_ci,COERCIBLE)
    for operation '='")

producing 500s on ``/accounts/login/`` and a silent index-loss on every
other comparison against those columns (implicit charset conversion
disables index usage).

This migration runs ``ALTER TABLE <name> CONVERT TO CHARACTER SET
utf8mb4 COLLATE utf8mb4_unicode_ci`` on each affected table that (a)
exists in the schema and (b) is not already on ``utf8mb4``. It mirrors
the targeted pattern used by ``cases/0026_convert_utf8mb4`` and
``laws/0025_convert_utf8mb4``.

Idempotent: re-running after success is a no-op because the filter on
``information_schema.tables`` excludes already-converted tables.

Reverse migration is a documented no-op: charset conversion of textual
columns is effectively irreversible (any bytes outside latin1 would be
lost on a backwards CONVERT).
"""

from __future__ import annotations

import logging

from django.db import migrations

logger = logging.getLogger(__name__)

# Tables touched by the auth/login flow that were created before
# utf8mb4 became the default. Each name is checked against
# information_schema.tables before ALTER so installs missing any of
# these (e.g. tests that haven't run the corresponding 3rd-party
# migrations) are tolerated.
TABLES = (
    "auth_user",
    "auth_group",
    "auth_permission",
    "auth_user_groups",
    "auth_user_user_permissions",
    "auth_group_permissions",
    "django_session",
    "account_emailaddress",
    "account_emailconfirmation",
    "socialaccount_socialaccount",
    "socialaccount_socialapp",
    "socialaccount_socialapp_sites",
    "socialaccount_socialtoken",
    "authtoken_token",
)

TARGET_CHARSET = "utf8mb4"
TARGET_COLLATION = "utf8mb4_unicode_ci"


def convert(apps, schema_editor):
    if schema_editor.connection.vendor != "mysql":
        return
    cursor = schema_editor.connection.cursor()
    cursor.execute(
        """
        SELECT table_name, table_collation
        FROM information_schema.tables
        WHERE table_schema = DATABASE()
          AND table_name IN %s
        """,
        [TABLES],
    )
    rows = cursor.fetchall()
    if not rows:
        logger.info(
            "convert_auth_tables_utf8mb4: none of the target tables exist; skipping"
        )
        return
    for name, collation in rows:
        if collation and collation.startswith(TARGET_CHARSET):
            logger.info(
                "convert_auth_tables_utf8mb4: %s already on %s; skipping",
                name,
                collation,
            )
            continue
        sql = (
            f"ALTER TABLE `{name}` CONVERT TO CHARACTER SET "
            f"{TARGET_CHARSET} COLLATE {TARGET_COLLATION}"
        )
        logger.info(
            "convert_auth_tables_utf8mb4: %s (%s) -> %s",
            name,
            collation,
            TARGET_COLLATION,
        )
        cursor.execute(sql)


def noop(apps, schema_editor):
    """Charset conversion of textual columns is effectively irreversible."""
    pass


class Migration(migrations.Migration):
    atomic = False  # ALTER TABLE on MySQL/MariaDB is not transactional.

    dependencies = [
        ("accounts", "0005_backfill_default_permission_group"),
    ]

    operations = [
        migrations.RunPython(convert, noop),
    ]
