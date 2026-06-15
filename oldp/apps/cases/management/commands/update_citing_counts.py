"""Recompute the denormalized ``Case.citing_cases_count`` counter.

How often is each case cited by *other* (accepted) cases? That reverse
count powers most-cited / landmark-precedent sorting, but computing it per
query is expensive (a join + distinct aggregate). So we denormalize it onto
``Case.citing_cases_count`` here, off the hot path (run nightly / after an
ingestion + reference-extraction pass), and mirror it into Elasticsearch via
``CaseIndex``.

Counting follows the same definition as the ES citation graph: the number
of *distinct accepted cases* whose reference markers point at this case
(``CaseReferenceMarker.referenced_by`` = the citing case;
``Reference.case`` = the cited case).

Usage::

    manage.py update_citing_counts            # recompute + write
    manage.py update_citing_counts --dry-run  # report, write nothing
"""

import time

from django.core.management.base import BaseCommand
from django.db.models import Count

from oldp.apps.cases.models import Case
from oldp.apps.references.models import CaseReferenceMarker


class Command(BaseCommand):
    help = "Recompute Case.citing_cases_count (reverse citation counter)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Compute and report, but do not write to the database.",
        )
        parser.add_argument(
            "--batch-size",
            type=int,
            default=2000,
            help="Rows per bulk_update batch (default 2000).",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        batch_size = options["batch_size"]

        t0 = time.time()
        self.stdout.write("Aggregating reverse citation counts…")
        # cited case id -> number of distinct accepted citing cases.
        rows = (
            CaseReferenceMarker.objects.filter(
                references__case__isnull=False,
                referenced_by__review_status="accepted",
            )
            .values("references__case_id")
            .annotate(n=Count("referenced_by_id", distinct=True))
        )
        counts = {r["references__case_id"]: r["n"] for r in rows}
        self.stdout.write(
            f"  {len(counts):,} cases are cited at least once ({time.time() - t0:.0f}s)"
        )

        if dry_run:
            top = sorted(counts.items(), key=lambda kv: -kv[1])[:10]
            self.stdout.write("Top cited (dry-run, nothing written):")
            for cid, n in top:
                self.stdout.write(f"  case {cid}: {n}")
            return

        # Zero out cases that are no longer cited (had a stale positive count).
        reset = (
            Case.objects.filter(citing_cases_count__gt=0)
            .exclude(id__in=counts.keys())
            .update(citing_cases_count=0)
        )

        # Write the new counts in batches via bulk_update.
        updated = 0
        buf = []
        for case_id, n in counts.items():
            buf.append(Case(id=case_id, citing_cases_count=n))
            if len(buf) >= batch_size:
                Case.objects.bulk_update(buf, ["citing_cases_count"])
                updated += len(buf)
                buf = []
        if buf:
            Case.objects.bulk_update(buf, ["citing_cases_count"])
            updated += len(buf)

        self.stdout.write(
            self.style.SUCCESS(
                f"Updated {updated:,} cited cases, reset {reset:,} stale to 0 "
                f"in {time.time() - t0:.0f}s. Reindex to mirror into ES."
            )
        )
