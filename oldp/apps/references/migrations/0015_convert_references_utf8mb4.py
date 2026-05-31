r"""Convert references_* tables to utf8mb4 (closes openlegaldata/oldp#229).

``process_cases ... extract_refs`` fails on every row whose extracted
marker text contains a 3-byte UTF-8 character (THIN SPACE U+2009,
NARROW NO-BREAK SPACE U+202F, etc.) because the
``references_casereferencemarker.text`` column — and the sibling
``references_lawreferencemarker`` / ``references_reference`` tables —
were created when the MariaDB default was a narrow charset (latin1
in our case). Without this conversion roughly 14% of the post-#228
backfill of ``cases_case.references_extracted_at IS NULL`` rows
hard-fail with::

    MySQLdb.OperationalError (1366, "Incorrect string value:
    '\\xE2\\x80\\x89...' for column
    `oldp`.`references_casereferencemarker`.`text` at row N")

Mirrors the pattern of ``cases/0026_convert_utf8mb4`` and
``laws/0025_convert_utf8mb4``, but with one important difference:
``references_casereferencemarker`` is the marker table for ~17 M rows
in production, so the ALTER may take real time. The migration is
marked ``atomic = False`` and the SQL is emitted as
``ALGORITHM=INPLACE, LOCK=NONE`` where supported, falling back to a
plain ALTER if the server rejects the algorithm hint.

Idempotent: skips tables already on ``utf8mb4`` via
``information_schema.tables.table_collation``. Reverse is a documented
no-op — see the other utf8mb4 conversion migrations in this repo.
"""

from __future__ import annotations

import logging

from django.db import migrations

logger = logging.getLogger(__name__)

# Tables affected by issue #229. The marker tables are the ones that
# actually break extraction; ``references_reference`` is included for
# consistency so future schema queries don't need to discriminate by
# charset.
TABLES = (
    "references_casereferencemarker",
    "references_lawreferencemarker",
    "references_reference",
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
        logger.info("convert_references_utf8mb4: no target tables in schema; skipping")
        return
    for name, collation in rows:
        if collation and collation.startswith(TARGET_CHARSET):
            logger.info(
                "convert_references_utf8mb4: %s already on %s; skipping",
                name,
                collation,
            )
            continue
        # Prefer the in-place / no-lock algorithm where the server
        # supports it (MariaDB 10.3+, MySQL 8). If the engine rejects
        # those hints (e.g. because of a unique index on the converted
        # column that would need a copy), fall back to a plain
        # ALTER, which copies the table.
        sql_inplace = (
            f"ALTER TABLE `{name}` "
            f"CONVERT TO CHARACTER SET {TARGET_CHARSET} COLLATE {TARGET_COLLATION}, "
            f"ALGORITHM=INPLACE, LOCK=NONE"
        )
        sql_copy = (
            f"ALTER TABLE `{name}` "
            f"CONVERT TO CHARACTER SET {TARGET_CHARSET} COLLATE {TARGET_COLLATION}"
        )
        try:
            logger.info(
                "convert_references_utf8mb4: %s (%s) -> %s (INPLACE/NONE)",
                name,
                collation,
                TARGET_COLLATION,
            )
            cursor.execute(sql_inplace)
        except Exception as exc:  # noqa: BLE001 — fall back regardless
            logger.warning(
                "convert_references_utf8mb4: INPLACE failed on %s (%s); "
                "falling back to copying ALTER",
                name,
                exc,
            )
            cursor.execute(sql_copy)


def noop(apps, schema_editor):
    """Charset conversion of textual columns is effectively irreversible."""
    pass


class Migration(migrations.Migration):
    atomic = False  # ALTER TABLE on MySQL/MariaDB is implicitly committing.

    dependencies = [
        ("references", "0014_backfill_reference_law_slugs"),
    ]

    operations = [
        migrations.RunPython(convert, noop),
    ]
