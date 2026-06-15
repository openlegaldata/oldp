"""Repair the ``latest=True`` flag so it tracks the newest *accepted* revision.

The latest-revision invariant (owned by
:meth:`oldp.apps.laws.models.LawBook.refresh_latest_for_code`, consumed by
``oldp.apps.laws.views.get_latest_law_book`` and ``Law.get_latest_revision_url``)
is: for every book ``code`` with an accepted revision, exactly one row — the
newest accepted one (by ``revision_date``, tiebreak: highest ``pk``) — is
flagged ``latest=True``; codes with no accepted revision have no flagged row.

A book can drift out of that state, e.g. ``Grundgesetz``/``GG``:

* a newer revision ingested via the API holds ``latest=True`` while still
  ``pending`` review, and the published accepted revision is ``latest=False`` —
  so the public sees *no* accepted latest (the original bug); or
* zero revisions are flagged at all (an old ingest/dedupe left it unset).

This command is the repair counterpart to ``dedupe_latest_books`` (which fixes
the *more than one* ``latest=True`` case). It recomputes the invariant for every
code and fixes any that are off. ``--dry-run`` reports without writing.

Usage:
    ./manage.py backfill_latest_books            # apply
    ./manage.py backfill_latest_books --dry-run  # report only
"""

from __future__ import annotations

import logging

from django.core.management import BaseCommand
from django.db import transaction

from oldp.apps.laws.models import LawBook

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Repair latest=True so it tracks the newest accepted revision per code."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report books needing repair without modifying the database.",
        )

    def handle(self, *args, dry_run: bool = False, **options):
        codes = LawBook.objects.order_by().values_list("code", flat=True).distinct()

        # (code, target_row_or_None, current_latest_pks) for each code that is
        # not already in the correct state.
        repairs = []
        for code in codes:
            target = (
                LawBook.objects.filter(code=code, review_status="accepted")
                .order_by("-revision_date", "-pk")
                .first()
            )
            current = set(
                LawBook.objects.filter(code=code, latest=True).values_list(
                    "pk", flat=True
                )
            )
            target_pks = {target.pk} if target is not None else set()
            if current != target_pks:
                repairs.append((code, target, current))

        if not repairs:
            self.stdout.write("No books missing a correct latest=True row.")
            return

        self.stdout.write(f"Found {len(repairs)} code(s) needing a latest-flag repair:")

        total_set = 0
        with transaction.atomic():
            for code, target, current in repairs:
                if target is None:
                    self.stdout.write(
                        f"  {code}: no accepted revision — clearing "
                        f"{len(current)} stale latest flag(s)"
                    )
                else:
                    self.stdout.write(
                        f"  {code}: flagging pk={target.pk} "
                        f"(revision_date={target.revision_date}) as latest"
                    )
                if not dry_run:
                    LawBook.refresh_latest_for_code(code)
                    if target is not None:
                        total_set += 1

        if dry_run:
            self.stdout.write(self.style.WARNING("Dry run — no changes written."))
        else:
            self.stdout.write(
                self.style.SUCCESS(f"Set latest=True on {total_set} row(s).")
            )
