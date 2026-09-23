"""Re-extract references for a scoped set of laws or cases.

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
between would leave that document with no references at all.

The case step additionally strips legacy ``[ref=UUID]`` brackets from
``content``. No case in the corpus still carries them, so this is a no-op in
practice, but the content is compared and only written when it actually
changed -- re-saving a large TEXT column on every document otherwise.
"""

import logging

from django.core.management.base import BaseCommand
from django.db import connection, transaction

from oldp.apps.cases.models import Case
from oldp.apps.laws.models import Law
from oldp.apps.processing.errors import ProcessingError

logger = logging.getLogger(__name__)

#: Markers whose text names two sections with "und" but hold more than two
#: references -- the signature of the misparse.
UND_SIGNATURE = r"^§§ [0-9]+ und [0-9]+"


#: Per-kind wiring: model, marker table, and the m2m FK column on it.
KINDS = {
    "law": (Law, "lawreferencemarker", "lawreferencemarker_id"),
    "case": (Case, "casereferencemarker", "casereferencemarker_id"),
}


class Command(BaseCommand):
    help = "Re-extract references for documents affected by the range misparse"

    def add_arguments(self, parser):
        parser.add_argument(
            "--kind",
            choices=sorted(KINDS),
            required=True,
            help="Which content type to re-extract.",
        )
        parser.add_argument(
            "--ids",
            nargs="+",
            type=int,
            help="Explicit ids; defaults to every affected document.",
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

    def _affected_ids(self, table, fk):
        sql = f"""
            SELECT DISTINCT m.referenced_by_id
            FROM references_{table} m
            JOIN (
                SELECT {fk} AS mid, COUNT(*) n
                FROM references_{table}_references
                GROUP BY {fk}
                HAVING n > 2
            ) c ON c.mid = m.id
            WHERE m.text REGEXP %s
        """
        with connection.cursor() as cur:
            cur.execute(sql, [UND_SIGNATURE])
            return [row[0] for row in cur.fetchall()]

    def _ref_count(self, table, fk, doc_ids=None):
        sql = f"""
            SELECT COUNT(*)
            FROM references_{table}_references j
            JOIN references_{table} m
              ON m.id = j.{fk}
        """
        params = []
        if doc_ids is not None:
            placeholders = ",".join(["%s"] * len(doc_ids))
            sql += f" WHERE m.referenced_by_id IN ({placeholders})"
            params = list(doc_ids)
        with connection.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchone()[0]

    def handle(self, *args, **options):
        kind = options["kind"]
        model, table, fk = KINDS[kind]

        if kind == "law":
            from oldp.apps.laws.processing.processing_steps.extract_refs import (
                ProcessingStep,
            )

            step = ProcessingStep()
        else:
            from oldp.apps.cases.processing.processing_steps.extract_refs import (
                ProcessingStep,
            )

            step = ProcessingStep(law_refs=True, case_refs=True, assign_refs=True)

        ids = options["ids"] or self._affected_ids(table, fk)
        if options["limit"]:
            ids = ids[: options["limit"]]

        if not ids:
            self.stdout.write(self.style.SUCCESS("Nothing to do."))
            return

        before = self._ref_count(table, fk, ids)
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

        done = failed = 0
        every = options["progress_every"]

        related = ["book"] if kind == "law" else ["court"]
        for doc in model.objects.filter(id__in=ids).select_related(*related).iterator():
            original_content = doc.content
            try:
                with transaction.atomic():
                    step.process(doc)
                    fields = ["references_extracted_at"]
                    if doc.content != original_content:
                        fields.append("content")
                    doc.save(update_fields=fields)
                done += 1
            except ProcessingError as exc:
                failed += 1
                logger.warning("Re-extraction failed for %s %s: %s", kind, doc.id, exc)
                self.stdout.write(
                    self.style.WARNING(f"  {kind} {doc.id}: ProcessingError: {exc}")
                )
                continue
            except Exception as exc:  # noqa: BLE001 - one bad document must not
                # abort a 2,000-document run; the transaction above already
                # rolled this law back to its previous markers.
                failed += 1
                logger.warning("Re-extraction failed for %s %s: %s", kind, doc.id, exc)
                self.stdout.write(
                    self.style.WARNING(
                        f"  {kind} {doc.id}: {type(exc).__name__}: {exc}"
                    )
                )

            if every and (done + failed) % every == 0:
                self.stdout.write(f"  ... {done + failed}/{len(ids)}")

        after = self._ref_count(table, fk, ids)
        self.stdout.write(
            self.style.SUCCESS(
                f"Re-extracted {done} document(s)"
                + (f", {failed} failure(s)" if failed else "")
                + f" | references {before} -> {after} ({after - before:+d})"
            )
        )
