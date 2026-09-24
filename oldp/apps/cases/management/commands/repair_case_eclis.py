"""Repair case ECLIs that upstream portals got wrong (#255).

Two defects, both copied verbatim from the source portals:

* **Repeated prefix** — the Hessen portal renders ``ECLI:ECLI:DE:…``. The
  prefix is collapsed; the rest of the ECLI is kept.
* **Another decision's ECLI** — the Berlin portal swaps ECLIs between
  decisions, NI-VORIS attaches ECLIs of other states' courts. An ECLI that
  contradicts its case (see :func:`oldp.apps.cases.ecli.ecli_contradicts_case`)
  is cleared, but only when OLDP holds the decision the ECLI really belongs
  to: same court code, same date, matching docket. If that owner is left
  without an ECLI, it gets this one — which puts swapped pairs back. Without
  an owner the row is only listed, for a human to check: an ECLI is never
  cleared on the strength of the heuristic alone.

Reports by default, writes only under ``--write``. Only ``ecli`` is written,
so ``updated_date`` and the URL (slug) stay as they are. See
``docs/data-repairs.md``.
"""

from collections import Counter

from django.core.management import BaseCommand

from oldp.apps.cases.ecli import (
    docket_matches,
    ecli_contradicts_case,
    normalize_ecli,
    parse_ecli,
)
from oldp.apps.cases.models import Case

SUMMARY_ROWS = (
    ("scanned", "Cases with an ECLI"),
    ("prefix_fixed", "Repeated prefix collapsed"),
    ("cleared", "Wrong ECLI cleared (owner found)"),
    ("unresolved", "Wrong ECLI kept (no owner found)"),
    ("moved", "Cleared ECLI given to its owner"),
)


class Command(BaseCommand):
    help = "Collapse repeated ECLI prefixes and clear ECLIs that belong to another case"

    def add_arguments(self, parser):
        parser.add_argument(
            "--write",
            action="store_true",
            help="Apply the changes. Without it the command only reports.",
        )

    def handle(self, *args, **options):
        write = options["write"]
        counters = Counter()
        # pk -> the ECLI the case ends up with. Planned in full before
        # anything is written, because a move depends on what the owner's
        # own ECLI becomes (the Berlin swaps clear both sides of a pair).
        plan = {}
        moves = []  # (ecli, owner case)

        rows = (
            Case.objects.exclude(ecli__isnull=True)
            .exclude(ecli="")
            .order_by("pk")
            .values_list("pk", "ecli", "file_number", "date")
        )
        for pk, ecli, file_number, date in rows.iterator():
            counters["scanned"] += 1
            new_ecli = normalize_ecli(ecli)
            if new_ecli != ecli:
                counters["prefix_fixed"] += 1

            if ecli_contradicts_case(new_ecli, file_number, date):
                owner = self._owner(new_ecli, exclude_pk=pk)
                if owner is None:
                    counters["unresolved"] += 1
                    self.stdout.write(
                        f"  keep   case={pk} {file_number!r} {date}: {new_ecli}"
                        " (no case matches it — check by hand)"
                    )
                else:
                    counters["cleared"] += 1
                    self.stdout.write(
                        f"  clear  case={pk} {file_number!r} {date}: {new_ecli}"
                        f" belongs to case={owner.pk} {owner.file_number!r} {owner.date}"
                    )
                    moves.append((new_ecli, owner))
                    new_ecli = ""

            if new_ecli != ecli:
                plan[pk] = new_ecli

        # Hand a cleared ECLI to its owner when the owner is left without one.
        for ecli, owner in moves:
            if plan.get(owner.pk, normalize_ecli(owner.ecli)) == "":
                plan[owner.pk] = ecli
                counters["moved"] += 1
                self.stdout.write(f"  move   {ecli} to case={owner.pk}")

        if write:
            for pk, new_ecli in plan.items():
                case = Case.objects.defer("content").get(pk=pk)
                case.ecli = new_ecli
                # ``ecli`` only: no ``updated_date`` bump, so the corrected
                # rows do not flood the "recent cases" list.
                case.save(update_fields=["ecli"])

        width = max(len(label) for _, label in SUMMARY_ROWS) + 1
        for key, label in SUMMARY_ROWS:
            self.stdout.write(f"{label + ':':<{width}} {counters[key]}")
        if not write:
            self.stdout.write(
                "Report only: no rows were written. Pass --write to apply."
            )

    @staticmethod
    def _owner(ecli, exclude_pk):
        """The one case the ECLI describes, or ``None``.

        Same court code, same decision date and a matching docket. Anything
        but exactly one such case is no evidence the ECLI is misplaced.
        """
        court, ecli_date, docket = parse_ecli(ecli)
        if ecli_date is None:
            return None
        candidates = [
            c
            for c in Case.objects.filter(court__code__iexact=court, date=ecli_date)
            .exclude(pk=exclude_pk)
            .only("pk", "file_number", "date", "ecli")
            if docket_matches(docket, c.file_number)
        ]
        return candidates[0] if len(candidates) == 1 else None
