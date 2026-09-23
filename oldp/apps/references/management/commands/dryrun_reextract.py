"""Report what a re-extraction would change, without writing anything.

Re-extraction is destructive by nature -- it deletes a document's markers and
their references before writing new ones -- so there is no way to preview it
from the real code path. This replays the same extraction and applies the same
persistence rules (short-form citations skipped, co-located citations grouped
by span, groups capped, over-long markers dropped) to count what *would* be
written, then diffs that against what is stored now.

Nothing is saved; the command opens no transaction and calls no save path.
"""

import logging

from django.core.management.base import BaseCommand
from django.db import connection
from refex.document import make_document

from oldp.apps.cases.models import Case
from oldp.apps.laws.models import Law

logger = logging.getLogger(__name__)

UND_SIGNATURE = r"^§§ [0-9]+ und [0-9]+"


class Command(BaseCommand):
    help = "Preview the effect of re-extracting references (writes nothing)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--kind",
            choices=("law", "case", "both"),
            default="both",
            help="Which content type to preview.",
        )
        parser.add_argument(
            "--sample",
            type=int,
            default=0,
            help="Only inspect this many documents per kind (0 = all).",
        )
        parser.add_argument(
            "--show",
            type=int,
            default=10,
            help="How many per-document lines to print.",
        )

    def _affected_ids(self, table, fk_column):
        """Documents holding an `§§ N und M` marker with more than two refs."""
        sql = f"""
            SELECT DISTINCT m.referenced_by_id
            FROM references_{table} m
            JOIN (
                SELECT {fk_column} AS mid, COUNT(*) n
                FROM references_{table}_references
                GROUP BY {fk_column}
                HAVING n > 2
            ) c ON c.mid = m.id
            WHERE m.text REGEXP %s
        """
        with connection.cursor() as cur:
            cur.execute(sql, [UND_SIGNATURE])
            return [row[0] for row in cur.fetchall()]

    def _would_write(self, step, content, referenced_by):
        """Reference rows a re-extraction would persist for this document."""
        document = make_document(content or "", fmt="html")
        result = step.extractor.extract(document)

        max_len = min(
            step.marker_model._meta.get_field("text").max_length,
            1000,
        )
        markers = 0
        refs = 0
        for _key, group in step._group_by_span(result.citations):
            if not group:
                continue
            group = step._cap_group(group, referenced_by)
            if len(group[0].span.text) > max_len:
                continue
            markers += 1
            refs += len(group)
        return markers, refs

    def _preview(self, kind, ids, show):
        if kind == "law":
            from oldp.apps.laws.processing.processing_steps.extract_refs import (
                ProcessingStep,
            )

            step = ProcessingStep()
            model = Law
            marker_attr = "lawreferencemarker"
        else:
            from oldp.apps.cases.processing.processing_steps.extract_refs import (
                ProcessingStep,
            )

            step = ProcessingStep(law_refs=True, case_refs=True, assign_refs=True)
            model = Case
            marker_attr = "casereferencemarker"

        tot_before_m = tot_before_r = tot_after_m = tot_after_r = 0
        failures = 0
        printed = 0

        for obj in model.objects.filter(id__in=ids).iterator():
            before_m = getattr(obj, f"{marker_attr}_set").count()
            with connection.cursor() as cur:
                cur.execute(
                    f"""SELECT COUNT(*) FROM references_{marker_attr}_references j
                        JOIN references_{marker_attr} m ON m.id = j.{marker_attr}_id
                        WHERE m.referenced_by_id = %s""",
                    [obj.id],
                )
                before_r = cur.fetchone()[0]

            if kind == "law":
                step.law_engine.law_book_context = obj.book.code

            try:
                after_m, after_r = self._would_write(step, obj.content, obj)
            except Exception as exc:  # noqa: BLE001 - reporting, not handling
                failures += 1
                self.stdout.write(
                    self.style.WARNING(f"  {kind} {obj.id}: extraction failed: {exc}")
                )
                continue

            tot_before_m += before_m
            tot_before_r += before_r
            tot_after_m += after_m
            tot_after_r += after_r

            if printed < show and before_r != after_r:
                printed += 1
                self.stdout.write(
                    f"  {kind} {obj.id}: markers {before_m} -> {after_m}, "
                    f"refs {before_r} -> {after_r} ({after_r - before_r:+d})"
                )

        self.stdout.write(
            self.style.SUCCESS(
                f"{kind}: {len(ids)} document(s) | "
                f"markers {tot_before_m} -> {tot_after_m} "
                f"({tot_after_m - tot_before_m:+d}) | "
                f"refs {tot_before_r} -> {tot_after_r} "
                f"({tot_after_r - tot_before_r:+d})"
                + (f" | {failures} extraction failure(s)" if failures else "")
            )
        )

    def handle(self, *args, **options):
        kind = options["kind"]
        sample = options["sample"]
        show = options["show"]

        plan = []
        if kind in ("law", "both"):
            plan.append(
                (
                    "law",
                    self._affected_ids("lawreferencemarker", "lawreferencemarker_id"),
                )
            )
        if kind in ("case", "both"):
            plan.append(
                (
                    "case",
                    self._affected_ids("casereferencemarker", "casereferencemarker_id"),
                )
            )

        for k, ids in plan:
            if sample:
                ids = ids[:sample]
            self.stdout.write(f"--- {k}: {len(ids)} affected document(s) ---")
            self._preview(k, ids, show)

        self.stdout.write(self.style.SUCCESS("Dry run complete — nothing was written."))
