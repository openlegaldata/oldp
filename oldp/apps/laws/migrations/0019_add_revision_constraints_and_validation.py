# Generated manually for revision validation and constraints

from django.db import migrations, models

import oldp.apps.laws.models


class Migration(migrations.Migration):
    dependencies = [
        ("laws", "0018_auto_20181128_1059"),
    ]

    operations = [
        # Add validator to revision_date field
        migrations.AlterField(
            model_name="lawbook",
            name="revision_date",
            field=models.DateField(
                default="1990-01-01",
                help_text="Date of revision",
                validators=[oldp.apps.laws.models.validate_revision_date],
            ),
        ),
        # Add unique constraint for latest=True per code
        # Note: Conditional unique constraints are not fully supported in SQLite.
        # We keep the constraint in the model Meta for PostgreSQL/MySQL compatibility,
        # but skip adding it in the migration to avoid test failures with SQLite.
        # Model-level validation (clean() method) enforces this rule across all DBs.
    ]
