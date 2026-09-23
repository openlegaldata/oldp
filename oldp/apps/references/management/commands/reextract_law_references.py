"""Re-extract law-to-law references for a scoped set of laws.

Written for the cleanup after legal-reference-extraction 0.5.4, which fixed two
parser defects that over-produced references: "und" was read as a range
separator ("§§ 627 und 1300" -> 674 rows instead of 2) and "bis" ranges were
unbounded. The rows already written stay wrong until the affected documents are
extracted again.

Trimming them is not an option for the "und" case: both endpoints name real
sections, so keeping only the first would delete a genuine citation. The rows
have to be rebuilt by the extractor.

Each document is processed in its own transaction. ``process()`` deletes a
document's markers before writing the new ones, so an unguarded failure in
between would leave that law with no references at all.
"""

import logging

from django.core.management.base import BaseCommand
from django.db import connection, transaction

from oldp.apps.laws.models import Law
from oldp.apps.processing.errors import ProcessingError

logger = logging.getLogger(__name__)

#: Markers whose text names two sections with "und" but hold more than two
#: references -- the signature of the misparse.
UND_SIGNATURE = r"^§§ [0-9]+ und [0-9]+"


class Command(BaseCommand):
    help = "Re-extract law references for documents affected by the range misparse"

    def add_arguments(self, parser):
        parser.add_argument(
            "--ids",
            nargs="+",
            type=int,
            help="Explicit law ids; defaults to every affected document.",
        )
        parser.add_argument(
            "--limit", type=int, default=None, help="Stop after this many documents."
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="List what would be processed without writing.",
        )
        parser.add_argument(
            "--progress-every",
            type=int,
            default=100,
            help="Emit a progress line every N documents.",
        )

    def _affected_ids(self):
        sql = """
            SELECT DISTINCT m.referenced_by_id
            FROM references_lawreferencemarker m
            JOIN (
                SELECT lawreferencemarker_id AS mid, COUNT(*) n
                FROM references_lawreferencemarker_references
                GROUP BY lawreferencemarker_id
                HAVING n > 2
            ) c ON c.mid = m.id
            WHERE m.text REGEXP %s
        """
        with connection.cursor() as cur:
            cur.execute(sql, [UND_SIGNATURE])
            return [row[0] for row in cur.fetchall()]

    def _ref_count(self, law_ids=None):
        sql = """
            SELECT COUNT(*)
            FROM references_lawreferencemarker_references j
            JOIN references_lawreferencemarker m
              ON m.id = j.lawreferencemarker_id
        """
        params = []
        if law_ids is not None:
            placeholders = ",".join(["%s"] * len(law_ids))
            sql += f" WHERE m.referenced_by_id IN ({placeholders})"
            params = list(law_ids)
        with connection.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchone()[0]

    def handle(self, *args, **options):
        from oldp.apps.laws.processing.processing_steps.extract_refs import (
            ProcessingStep,
        )

        ids = options["ids"] or self._affected_ids()
        if options["limit"]:
            ids = ids[: options["limit"]]

        if not ids:
            self.stdout.write(self.style.SUCCESS("Nothing to do."))
            return

        before = self._ref_count(ids)
        self.stdout.write(
            f"{len(ids)} document(s) hold {before} reference(s) before the run."
        )

        if options["dry_run"]:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Dry run — would re-extract {len(ids)} document(s); nothing written."
                )
            )
            return

        step = ProcessingStep()
        done = failed = 0
        every = options["progress_every"]

        for law in Law.objects.filter(id__in=ids).select_related("book").iterator():
            try:
                with transaction.atomic():
                    step.process(law)
                    law.save(update_fields=["references_extracted_at"])
                done += 1
            except ProcessingError as exc:
                failed += 1
                logger.warning("Re-extraction failed for law %s: %s", law.id, exc)
                self.stdout.write(
                    self.style.WARNING(f"  law {law.id}: ProcessingError: {exc}")
                )
                continue
            except Exception as exc:  # noqa: BLE001 - one bad document must not
                # abort a 2,000-document run; the transaction above already
                # rolled this law back to its previous markers.
                failed += 1
                logger.warning("Re-extraction failed for law %s: %s", law.id, exc)
                self.stdout.write(
                    self.style.WARNING(f"  law {law.id}: {type(exc).__name__}: {exc}")
                )

            if every and (done + failed) % every == 0:
                self.stdout.write(f"  ... {done + failed}/{len(ids)}")

        after = self._ref_count(ids)
        self.stdout.write(
            self.style.SUCCESS(
                f"Re-extracted {done} document(s)"
                + (f", {failed} failure(s)" if failed else "")
                + f" | references {before} -> {after} ({after - before:+d})"
            )
        )
