"""Report cases whose ECLI names a different court than the one assigned.

Why this exists
---------------
``reassign_courts_from_ecli`` repairs a hand-picked list of court pairs,
and the comment defending that list carried numbers from a one-off audit
that nothing in the repository could reproduce. This command is that
audit, so the pairs are a result rather than a recollection.

Read-only. It never touches a row.

What "mismatch" means here
--------------------------
``ECLI:DE:<court>:<year>:<ordinal>`` carries the deciding court's
abbreviation, and ``CourtResolver._find_by_ecli`` resolves it by looking
that segment up against ``Court.code``, case-insensitively. A row is
reported when the segment and the assigned court's code differ.

A difference is not by itself a misfiled case, so each row is annotated:

* ``no Court with this code`` — the ECLI names an abbreviation that is not
  in the court table at all. Usually a different abbreviation scheme
  rather than a misfiled case; ``court_code_from_ecli`` only promises the
  segment equals ``Court.code`` for the federal courts.
* ``same court name`` — the two codes belong to ``Court`` rows sharing a
  name, e.g. AGGE1/AGGE2. Almost always duplicate court rows, meaning the
  case is filed correctly and the *court table* is what needs cleaning.
* ``ambiguous court code`` — more than one ``Court`` row carries this
  code, differing only in case. ``Court.code`` is unique, but not past
  case on every collation, and the lookups here are case-insensitive. The
  other annotations cannot be trusted for such a group, because they
  would be decided against whichever row was read last, so this one
  replaces them. Flagged whether or not the rows share a name, so that
  the audit annotates exactly the pairs ``reassign_courts_from_ecli``
  refuses to take.

Rows with no annotation are the candidates worth looking at, and the pair
in ``reassign_courts_from_ecli.DEFAULT_PAIRS`` should be among them.

Usage
-----
::

    # Full corpus, 50 largest groups
    manage.py audit_ecli_court_mismatch

    # Everything, however long the tail
    manage.py audit_ecli_court_mismatch --top 0

    # Only groups worth a repair pair
    manage.py audit_ecli_court_mismatch --min-rows 100

The percentages move with the corpus, so the output is worth dating
whenever it is quoted somewhere.
"""

import logging
from collections import Counter

from django.core.management import BaseCommand, CommandError

from oldp.apps.cases.models import Case
from oldp.apps.cases.services.court_resolver import court_code_from_ecli
from oldp.apps.courts.models import Court

logger = logging.getLogger(__name__)

NOTE_UNKNOWN_CODE = "no Court with this code"
NOTE_SAME_NAME = "same court name — likely duplicate Court rows"
NOTE_AMBIGUOUS_CODE = "ambiguous court code — several Court rows differ only in case"

HEADERS = ("filed under", "ECLI says", "rows", "note")


class Command(BaseCommand):
    help = "Report cases whose ECLI names a different court than the one assigned"

    def add_arguments(self, parser):
        parser.add_argument(
            "--top",
            type=int,
            default=50,
            help="Print only the N largest groups (0 = all).",
        )
        parser.add_argument(
            "--min-rows",
            type=int,
            default=0,
            help="Skip groups smaller than this.",
        )

    def handle(self, *args, **options):
        for name in ("top", "min_rows"):
            if options[name] < 0:
                raise CommandError(f"--{name.replace('_', '-')} cannot be negative")

        # ``Court.code`` is unique, but a case-sensitive collation lets
        # ``VGBE`` and ``vgbe`` both exist, and every code comparison here
        # is case-insensitive. Collapsing them would decide the notes below
        # against whichever row came last, so they are collected instead.
        courts = {}
        ambiguous_codes = set()
        for code, name in Court.objects.values_list("code", "name"):
            key = (code or "").upper()
            if key in courts:
                ambiguous_codes.add(key)
            courts[key] = name

        scanned = 0
        with_ecli = 0
        mismatches = Counter()

        # Three narrow columns, no model instances: the whole corpus fits in
        # one pass without the ``content`` blobs that make ``Case`` expensive
        # to walk. ``order_by()`` clears ``Meta.ordering`` — sorting ~240k
        # rows by date before streaming is a filesort on MySQL, and the
        # grouping below discards the order anyway.
        rows = Case.objects.order_by().values_list("ecli", "court__code").iterator()
        for ecli, court_code in rows:
            scanned += 1
            segment = court_code_from_ecli(ecli)
            if not segment:
                continue
            with_ecli += 1
            if segment.upper() == (court_code or "").upper():
                continue
            mismatches[(court_code, segment.upper())] += 1

        self._write_totals(scanned, with_ecli, mismatches)
        self._write_table(
            mismatches, courts, ambiguous_codes, options["top"], options["min_rows"]
        )

    def _write_totals(self, scanned, with_ecli, mismatches):
        total = sum(mismatches.values())
        share = f"{total / scanned:.2%}" if scanned else "n/a"
        self.stdout.write(f"Cases scanned:             {scanned}")
        self.stdout.write(f"Cases with a usable ECLI:  {with_ecli}")
        self.stdout.write(f"ECLI disagrees with court: {total} ({share} of scanned)")
        self.stdout.write("")

    def _write_table(self, mismatches, courts, ambiguous_codes, top, min_rows):
        """Print the mismatch groups, largest first.

        Args:
            mismatches: ``Counter`` keyed by ``(assigned code, ECLI code)``.
            courts: ``{upper-case code: name}`` for every known court.
            ambiguous_codes: Upper-case codes carried by more than one
                differently named ``Court`` row.
            top: Print at most this many groups (0 = all).
            min_rows: Skip groups smaller than this.
        """
        groups = [
            (filed_under, ecli_says, count)
            for (filed_under, ecli_says), count in mismatches.most_common()
            if count >= min_rows
        ]
        hidden = len(groups) - top if top and len(groups) > top else 0
        if top:
            groups = groups[:top]

        table = [
            (
                filed_under or "",
                ecli_says,
                str(count),
                self._note(filed_under, ecli_says, courts, ambiguous_codes),
            )
            for filed_under, ecli_says, count in groups
        ]
        widths = [
            max(len(row[column]) for row in (HEADERS, *table))
            for column in range(len(HEADERS))
        ]
        for row in (HEADERS, *table):
            self.stdout.write(
                "  ".join(
                    cell.ljust(width) for cell, width in zip(row, widths)
                ).rstrip()
            )
        if hidden:
            self.stdout.write(
                f"... {hidden} smaller groups not shown (--top 0 for all)"
            )

    @staticmethod
    def _note(filed_under, ecli_says, courts, ambiguous_codes):
        """Explain away the differences that are not misfiled cases."""
        # First, and instead of the rest: with two rows behind one code
        # every other answer here is drawn from an arbitrary one of them.
        if {ecli_says, (filed_under or "").upper()} & ambiguous_codes:
            return NOTE_AMBIGUOUS_CODE
        ecli_name = courts.get(ecli_says)
        if ecli_name is None:
            return NOTE_UNKNOWN_CODE
        assigned_name = courts.get((filed_under or "").upper())
        if assigned_name is not None and assigned_name.lower() == ecli_name.lower():
            return NOTE_SAME_NAME
        return ""
