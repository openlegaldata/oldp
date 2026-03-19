"""Convert cases_case text columns to utf8mb4 to support full Unicode.

Fixes MySQLdb.OperationalError (1366, "Incorrect string value") for characters
like − (U+2212), ‒ (U+2012), € (U+20AC), and mathematical symbols that
require 4-byte UTF-8 encoding.
"""

from django.db import migrations


def convert_to_utf8mb4(apps, schema_editor):
    """Convert text columns to utf8mb4 on MySQL/MariaDB."""
    if schema_editor.connection.vendor != "mysql":
        return

    cursor = schema_editor.connection.cursor()

    # Convert the entire table (all columns) to utf8mb4
    cursor.execute(
        "ALTER TABLE cases_case CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
    )


def noop(apps, schema_editor):
    """No-op reverse (charset conversion is effectively irreversible)."""
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("cases", "0025_review_status"),
    ]

    operations = [
        migrations.RunPython(convert_to_utf8mb4, noop),
    ]
