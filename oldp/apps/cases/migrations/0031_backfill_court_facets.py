"""Backfill the denormalised court facets on existing cases.

Done one court at a time rather than as a single ``UPDATE ... JOIN`` over all
425k rows: ``court_id`` is indexed, courts are few (~1.2k) and the largest owns
far less than the whole table, so this keeps each statement's lock short
instead of holding one write lock across the entire table.

Courts whose facets are both NULL are skipped -- the columns already default
to NULL, so those rows need no write at all.
"""

from django.db import migrations

#: Courts per query when reading the court table.
COURT_CHUNK = 500


def backfill(apps, schema_editor):
    Court = apps.get_model("courts", "Court")
    Case = apps.get_model("cases", "Case")

    courts = Court.objects.exclude(
        jurisdiction__isnull=True, level_of_appeal__isnull=True
    ).values_list("id", "jurisdiction", "level_of_appeal")

    for court_id, jurisdiction, level_of_appeal in courts.iterator(
        chunk_size=COURT_CHUNK
    ):
        Case.objects.filter(court_id=court_id).update(
            court_jurisdiction=jurisdiction,
            court_level_of_appeal=level_of_appeal,
        )


def unbackfill(apps, schema_editor):
    """Reversible: the columns are pure derived data."""
    Case = apps.get_model("cases", "Case")
    Case.objects.exclude(
        court_jurisdiction__isnull=True, court_level_of_appeal__isnull=True
    ).update(court_jurisdiction=None, court_level_of_appeal=None)


class Migration(migrations.Migration):
    dependencies = [
        ("cases", "0030_case_court_jurisdiction_case_court_level_of_appeal_and_more"),
        ("courts", "0001_initial"),
    ]

    operations = [migrations.RunPython(backfill, unbackfill)]
