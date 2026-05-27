"""Convert ``laws_law`` and ``laws_lawbook`` text columns to utf8mb4.

Mirrors ``cases/migrations/0026_convert_utf8mb4.py``.

Without this conversion, MariaDB-backed deployments where the laws
tables were originally created under a narrower default charset
(``latin1`` / ``utf8mb3``) raise
``MySQLdb.OperationalError (1366, "Incorrect string value")`` when
ingesting EU regulations whose German translations carry foreign
glyphs (e.g. Hungarian ``ő`` U+0151) or typographically heavy
punctuation (``„`` U+201E, ``“`` U+201C, ``—`` U+2014). The DRF
``LawViewSet.create`` does not catch ``DataError``/``OperationalError``,
so the failure surfaces to clients as an opaque HTTP 500.

Trigger that exposed the bug in production:
``POST /api/laws/`` for Brüssel-Ia-VO (CELEX 32012R1215) Art. 3
returns 500 because the German body contains Hungarian
("``közjegyző``") and Swedish ("``betalningsföreläggande``") legal
terminology plus directional quote marks.

The conversion is a metadata + data rewrite of the existing rows; on
deployments that already use utf8mb4 the ``ALTER TABLE`` is
effectively a no-op. SQLite (tests) and Postgres are skipped.
"""

from django.db import migrations


def convert_to_utf8mb4(apps, schema_editor):
    """Convert ``laws_law`` and ``laws_lawbook`` columns to utf8mb4."""
    if schema_editor.connection.vendor != "mysql":
        return

    cursor = schema_editor.connection.cursor()
    cursor.execute(
        "ALTER TABLE laws_law CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
    )
    cursor.execute(
        "ALTER TABLE laws_lawbook CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
    )


def noop(apps, schema_editor):
    """No-op reverse (charset conversion is effectively irreversible)."""
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("laws", "0024_law_references_extracted_at"),
    ]

    operations = [
        migrations.RunPython(convert_to_utf8mb4, noop),
    ]
