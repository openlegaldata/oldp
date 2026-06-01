"""Resolve duplicate ``latest=True`` rows in ``laws_lawbook``.

``oldp.apps.laws.views.get_latest_law_book`` queries
``LawBook.objects.filter(slug=book_slug, latest=True)`` and warns
``Book has more than one instance with latest=true: <slug>`` whenever
that query returns more than one row. In production we see this for
slugs like ``gg`` and ``uag``, which means two revisions of the same
slug both carry ``latest=True``.

This command finds slugs with more than one ``latest=True`` row, keeps
the row with the latest ``revision_date`` (tiebreak: highest ``pk``),
and unsets ``latest`` on the rest. ``--dry-run`` reports what would
change without writing.

Usage:
    ./manage.py dedupe_latest_books            # apply
    ./manage.py dedupe_latest_books --dry-run  # report only
"""

from __future__ import annotations

import logging

from django.core.management import BaseCommand
from django.db import transaction
from django.db.models import Count

from oldp.apps.laws.models import LawBook

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Resolve duplicate latest=True LawBook rows (per slug)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report duplicates without modifying the database.",
        )

    def handle(self, *args, dry_run: bool = False, **options):
        duplicate_slugs = list(
            LawBook.objects.filter(latest=True)
            .values("slug")
            .annotate(n=Count("id"))
            .filter(n__gt=1)
            .values_list("slug", "n")
        )

        if not duplicate_slugs:
            self.stdout.write("No duplicate latest=True rows found.")
            return

        self.stdout.write(
            f"Found {len(duplicate_slugs)} slug(s) with duplicate latest=True:"
        )
        for slug, n in duplicate_slugs:
            self.stdout.write(f"  {slug}: {n} rows")

        total_unset = 0
        with transaction.atomic():
            for slug, _ in duplicate_slugs:
                rows = list(
                    LawBook.objects.filter(slug=slug, latest=True)
                    .order_by("-revision_date", "-pk")
                    .values_list("pk", "revision_date")
                )
                keeper_pk, keeper_date = rows[0]
                losers = [pk for pk, _ in rows[1:]]
                self.stdout.write(
                    f"  {slug}: keeping pk={keeper_pk} "
                    f"(revision_date={keeper_date}); unsetting "
                    f"pk={','.join(str(p) for p in losers)}"
                )
                if not dry_run:
                    n = LawBook.objects.filter(pk__in=losers).update(latest=False)
                    total_unset += n

        if dry_run:
            self.stdout.write(self.style.WARNING("Dry run — no changes written."))
        else:
            self.stdout.write(
                self.style.SUCCESS(f"Unset latest on {total_unset} row(s).")
            )
