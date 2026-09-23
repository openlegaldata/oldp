"""Show the citations a case re-extraction would ADD, with surrounding context.

Read-only. Re-extraction on cases nets ~+4,000 references beyond the "und"
fix, which is recall improvement from the newer extractor rather than the
cleanup. Before acting on that, the added citations need checking: a newer
extractor finding *more* is exactly as likely to be a fresh over-extraction
mode as a genuine gain -- that is the failure this whole thread has been about.
"""

import html
import random
import re

from django.core.management.base import BaseCommand
from django.db import connection
from refex.document import make_document

from oldp.apps.cases.models import Case

UND_SIGNATURE = r"^§§ [0-9]+ und [0-9]+"


class Command(BaseCommand):
    help = "Sample citations a case re-extraction would add (writes nothing)"

    def add_arguments(self, parser):
        parser.add_argument("--docs", type=int, default=12)
        parser.add_argument("--per-doc", type=int, default=4)
        parser.add_argument("--seed", type=int, default=7)
        parser.add_argument("--context", type=int, default=90)

    def _affected_ids(self):
        sql = """
            SELECT DISTINCT m.referenced_by_id
            FROM references_casereferencemarker m
            JOIN (
                SELECT casereferencemarker_id AS mid, COUNT(*) n
                FROM references_casereferencemarker_references
                GROUP BY casereferencemarker_id HAVING n > 2
            ) c ON c.mid = m.id
            WHERE m.text REGEXP %s
        """
        with connection.cursor() as cur:
            cur.execute(sql, [UND_SIGNATURE])
            return [r[0] for r in cur.fetchall()]

    @staticmethod
    def _plain(content):
        text = re.sub(r"<[^>]+>", " ", content or "")
        return html.unescape(re.sub(r"\s+", " ", text))

    def handle(self, *args, **opts):
        from oldp.apps.cases.processing.processing_steps.extract_refs import (
            ProcessingStep,
        )

        step = ProcessingStep(law_refs=True, case_refs=True, assign_refs=True)
        ids = self._affected_ids()
        random.Random(opts["seed"]).shuffle(ids)

        added_total = removed_total = 0
        shown = 0

        for case in Case.objects.filter(id__in=ids[: opts["docs"]]).iterator():
            stored = {
                (m.text, m.start)
                for m in case.casereferencemarker_set.all()
            }
            document = make_document(case.content or "", fmt="html")
            result = step.extractor.extract(document)

            proposed = []
            for _k, group in step._group_by_span(result.citations):
                if not group:
                    continue
                group = step._cap_group(group, case)
                span = group[0].span
                proposed.append((span.text, span.start, len(group)))

            proposed_keys = {(t, s) for t, s, _ in proposed}
            added = [p for p in proposed if (p[0], p[1]) not in stored]
            removed = [s for s in stored if s not in proposed_keys]
            added_total += len(added)
            removed_total += len(removed)

            if not added:
                continue

            plain = self._plain(case.content)
            self.stdout.write(
                f"\n=== case {case.id} ({case.file_number}) "
                f"+{len(added)} / -{len(removed)} ==="
            )
            for text, start, nrefs in added[: opts["per_doc"]]:
                idx = plain.find(text)
                if idx == -1:
                    ctx = "(context not located in plain text)"
                else:
                    c = opts["context"]
                    ctx = plain[max(0, idx - c) : idx + len(text) + c]
                    ctx = ctx.replace(text, f"[[{text}]]", 1)
                self.stdout.write(f"  ADDED {text!r} (refs={nrefs})")
                self.stdout.write(f"        …{ctx}…")
                shown += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"\nSampled {opts['docs']} document(s): "
                f"{added_total} marker(s) added, {removed_total} removed, "
                f"{shown} shown. Nothing written."
            )
        )
