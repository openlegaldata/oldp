"""Repair ``laws_lawbook`` rows that have revisions but no ``latest=True``.

The latest-revision resolution
(:meth:`oldp.apps.laws.models.LawBook.resolve_latest`, used by
``oldp.apps.laws.views.get_latest_law_book`` and
``Law.get_latest_revision_url``) expects every book code/slug with revisions
to have exactly one row flagged ``latest=True``. Some books
(e.g. ``Grundgesetz``/``gg``) can end up with revisions but *zero* ``latest=True``
rows — the latest flag was never set, or an ingest/dedupe left it unset. Those
books then render degraded and log a warning on every page render.

This command is the symmetric counterpart to ``dedupe_latest_books`` (which
fixes the *more than one* ``latest=True`` case): it finds codes that have rows
but none flagged ``latest=True``, and flags the newest revision by
``revision_date`` (tiebreak: highest ``pk``). ``--dry-run`` reports what would
change without writing.

Usage:
    ./manage.py backfill_latest_books            # apply
    ./manage.py backfill_latest_books --dry-run  # report only
"""

from __future__ import annotations

import logging

from django.core.management import BaseCommand
from django.db import transaction
from django.db.models import Count, Q

from oldp.apps.laws.models import LawBook

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Flag the newest revision as latest for books missing a latest=True row."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report missing-latest books without modifying the database.",
        )

    def handle(self, *args, dry_run: bool = False, **options):
        # Codes that have rows but zero latest=True rows.
        missing_codes = list(
            LawBook.objects.values("code")
            .annotate(n_latest=Count("pk", filter=Q(latest=True)))
            .filter(n_latest=0)
            .values_list("code", flat=True)
        )

        if not missing_codes:
            self.stdout.write("No books missing a latest=True row.")
            return

        self.stdout.write(
            f"Found {len(missing_codes)} code(s) with no latest=True row:"
        )

        total_set = 0
        with transaction.atomic():
            for code in missing_codes:
                newest = (
                    LawBook.objects.filter(code=code)
                    .order_by("-revision_date", "-pk")
                    .first()
                )
                self.stdout.write(
                    f"  {code}: flagging pk={newest.pk} "
                    f"(revision_date={newest.revision_date}) as latest"
                )
                if not dry_run:
                    # Use update() to bypass clean(); resolve_latest already
                    # guarantees the other rows for this code are latest=False.
                    LawBook.objects.filter(pk=newest.pk).update(latest=True)
                    total_set += 1

        if dry_run:
            self.stdout.write(self.style.WARNING("Dry run — no changes written."))
        else:
            self.stdout.write(
                self.style.SUCCESS(f"Set latest=True on {total_set} row(s).")
            )
