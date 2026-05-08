"""Backfill ``Reference.law_book_slug`` + ``law_section_slug`` from the existing ``law`` FK.

The slug pair is the new stable identifier for the cited law section
(see ``Reference.law`` field doc). For rows where the FK is set, copy
the linked ``Law``'s book slug + slug across so reverse-citation
queries can switch to slug-based filters without losing existing
data. Rows with ``law=NULL`` (unresolved citations) leave the slug
columns empty.

Runs in batches via ``Reference.objects.filter(law__isnull=False)``
joined to ``laws_law`` + ``laws_lawbook`` so each row's update is one
SQL statement; iterates in chunks to keep transactions bounded for
the 14k+ row corpus on the dev stack and the ~millions on prod.
"""

from __future__ import annotations

from django.db import migrations


def backfill_law_slugs(apps, schema_editor):
    Reference = apps.get_model("references", "Reference")

    qs = (
        Reference.objects.filter(law__isnull=False)
        .select_related("law", "law__book")
        .only("id", "law__slug", "law__book__slug")
    )

    BATCH = 5000
    pending: list = []
    for ref in qs.iterator(chunk_size=BATCH):
        ref.law_book_slug = ref.law.book.slug or ""
        ref.law_section_slug = ref.law.slug or ""
        pending.append(ref)
        if len(pending) >= BATCH:
            Reference.objects.bulk_update(
                pending, ["law_book_slug", "law_section_slug"]
            )
            pending.clear()
    if pending:
        Reference.objects.bulk_update(pending, ["law_book_slug", "law_section_slug"])


def reverse_backfill(apps, schema_editor):
    """No-op: leaving slugs populated when reverting is harmless and lets
    a re-applied migration short-circuit on already-populated rows.
    """


class Migration(migrations.Migration):
    dependencies = [
        ("references", "0013_add_reference_law_slugs"),
    ]

    operations = [
        migrations.RunPython(backfill_law_slugs, reverse_code=reverse_backfill),
    ]
