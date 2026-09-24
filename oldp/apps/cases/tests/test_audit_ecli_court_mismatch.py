"""Tests for the ``audit_ecli_court_mismatch`` management command.

The command exists to make the pair list in ``reassign_courts_from_ecli``
reproducible, so the tests care about two things: that a real misfiling is
reported, and that a difference the audit can explain away, or cannot
resolve at all, is annotated rather than counted as a finding.
"""

import re
from datetime import date
from io import StringIO

from django.core.management import CommandError, call_command
from django.db import connection
from django.test import TestCase, tag
from django.test.utils import CaptureQueriesContext

from oldp.apps.cases.models import Case
from oldp.apps.courts.models import Country, Court, State


@tag("commands")
class AuditEcliCourtMismatchTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        country, _ = Country.objects.get_or_create(
            code="DE", defaults={"name": "Germany"}
        )
        state, _ = State.objects.get_or_create(
            pk=1, defaults={"name": "Berlin", "country": country, "slug": "berlin"}
        )
        cls.state = state
        cls.ovg = cls._court("Oberverwaltungsgericht Berlin-Brandenburg", "OVGBEBB")
        cls.vg = cls._court("Verwaltungsgericht Berlin", "VGBE")
        # Two rows for one court — the AGGE1/AGGE2 shape.
        cls.ag_one = cls._court("Amtsgericht Geldern", "AGGE1")
        cls.ag_two = cls._court("Amtsgericht Geldern", "AGGE2")

    @classmethod
    def _court(cls, name, code):
        return Court.objects.create(
            name=name,
            slug=code.lower(),
            code=code,
            court_type=code[:3],
            state=cls.state,
        )

    def _case(self, court, ecli, file_number):
        case = Case(
            court=court,
            file_number=file_number,
            date=date(2018, 12, 20),
            content="<p>Test</p>",
            ecli=ecli,
        )
        case.set_slug()
        case.save()
        return case

    def _run(self, *args):
        out = StringIO()
        call_command("audit_ecli_court_mismatch", *args, stdout=out)
        return out.getvalue()

    def _rows(self, output):
        """Parse the table into ``{(filed under, ECLI says): (rows, note)}``."""
        parsed = {}
        for line in output.splitlines():
            cells = re.split(r" {2,}", line.strip())
            if len(cells) >= 3 and cells[2].isdigit():
                note = cells[3] if len(cells) > 3 else ""
                parsed[(cells[0], cells[1])] = (int(cells[2]), note)
        return parsed

    def test_real_mismatch_is_reported_without_a_note(self):
        """The shape the repair command exists for: OVG holding a VG case."""
        self._case(self.ovg, "ECLI:DE:VGBE:2018:1220.2K178.17.00", "2 K 178.17")
        self._case(self.ovg, "ECLI:DE:VGBE:2018:1220.2K179.17.00", "2 K 179.17")

        rows = self._rows(self._run())

        self.assertEqual(rows[("OVGBEBB", "VGBE")], (2, ""))

    def test_matching_ecli_is_not_reported(self):
        """A case whose ECLI names its own court is not a finding."""
        self._case(self.ovg, "ECLI:DE:OVGBEBB:2018:1220.OVG2N1.18.00", "OVG 2 N 1.18")

        output = self._run()

        self.assertEqual(self._rows(output), {})
        self.assertIn("ECLI disagrees with court: 0", output)

    def test_duplicate_court_rows_are_annotated(self):
        """Same name under two codes means the court table needs cleaning."""
        self._case(self.ag_one, "ECLI:DE:AGGE2:2018:1220.1C1.18.00", "1 C 1.18")

        rows = self._rows(self._run())

        count, note = rows[("AGGE1", "AGGE2")]
        self.assertEqual(count, 1)
        self.assertIn("duplicate", note)

    def test_code_ambiguous_apart_from_case_is_flagged_not_guessed(self):
        """Two rows behind one code make every other verdict arbitrary.

        The lookups here are case-insensitive while ``Court.code`` is
        unique only as written, so both rows can exist — and the note was
        decided against whichever of them the scan read last. With the
        rows named differently that is a choice between "" and "duplicate
        Court rows", settled by queryset order.
        """
        Court.objects.create(
            name="Oberverwaltungsgericht Berlin-Brandenburg",
            slug="vgbe-second-row",
            code="vgbe",
            court_type="VG",
            state=self.state,
        )
        self._case(self.ovg, "ECLI:DE:VGBE:2018:1220.1C1.18.00", "1 C 1.18")

        rows = self._rows(self._run())

        count, note = rows[("OVGBEBB", "VGBE")]
        self.assertEqual(count, 1)
        self.assertIn("ambiguous", note)

    def test_code_ambiguous_apart_from_case_is_flagged_even_with_one_name(self):
        """The annotation has to cover what the repair command refuses.

        ``_parse_pairs`` rejects a ``--pair`` whose code matches two rows
        whatever they are called. An audit that only flagged the
        differently named ones would present this group as a clean
        candidate and send an operator into that rejection.
        """
        Court.objects.create(
            name="Verwaltungsgericht Berlin",
            slug="vgbe-same-name-row",
            code="vgbe",
            court_type="VG",
            state=self.state,
        )
        self._case(self.ovg, "ECLI:DE:VGBE:2018:1220.1C1.18.00", "1 C 1.18")

        rows = self._rows(self._run())

        count, note = rows[("OVGBEBB", "VGBE")]
        self.assertEqual(count, 1)
        self.assertIn("ambiguous", note)

    def test_unknown_ecli_code_is_annotated(self):
        """An abbreviation absent from the court table is not a misfiling."""
        self._case(self.ovg, "ECLI:DE:NOSUCH:2018:1220.1C1.18.00", "1 C 1.18")

        rows = self._rows(self._run())

        self.assertEqual(rows[("OVGBEBB", "NOSUCH")], (1, "no Court with this code"))

    def test_case_without_a_usable_ecli_is_counted_apart(self):
        """No ECLI is not a disagreement — it says nothing either way."""
        self._case(self.ovg, "", "1 C 2.18")
        self._case(self.ovg, "ECLI:DE:VGBE:2018:1220.1C3.18.00", "1 C 3.18")

        output = self._run()

        self.assertIn("Cases scanned:             2", output)
        self.assertIn("Cases with a usable ECLI:  1", output)
        self.assertIn("ECLI disagrees with court: 1", output)

    def test_min_rows_hides_the_tail(self):
        self._case(self.ovg, "ECLI:DE:VGBE:2018:1220.2K1.17.00", "2 K 1.17")
        self._case(self.ovg, "ECLI:DE:VGBE:2018:1220.2K2.17.00", "2 K 2.17")
        self._case(self.ovg, "ECLI:DE:NOSUCH:2018:1220.1C1.18.00", "1 C 1.18")

        rows = self._rows(self._run("--min-rows", "2"))

        self.assertIn(("OVGBEBB", "VGBE"), rows)
        self.assertNotIn(("OVGBEBB", "NOSUCH"), rows)

    def test_top_caps_the_table_and_says_so(self):
        self._case(self.ovg, "ECLI:DE:VGBE:2018:1220.2K1.17.00", "2 K 1.17")
        self._case(self.ovg, "ECLI:DE:VGBE:2018:1220.2K2.17.00", "2 K 2.17")
        self._case(self.ovg, "ECLI:DE:NOSUCH:2018:1220.1C1.18.00", "1 C 1.18")

        output = self._run("--top", "1")

        self.assertIn(("OVGBEBB", "VGBE"), self._rows(output))
        self.assertIn("1 smaller groups not shown", output)

    def test_negative_top_is_rejected(self):
        """It would drop one group while claiming to have hidden all of them."""
        with self.assertRaises(CommandError):
            self._run("--top", "-1")

    def test_negative_min_rows_is_rejected(self):
        with self.assertRaises(CommandError):
            self._run("--min-rows", "-1")

    def test_corpus_scan_is_not_sorted(self):
        """``Meta.ordering`` would filesort the whole table for nothing.

        The grouping is a ``Counter`` that ``most_common()`` re-sorts, so an
        ORDER BY on a ~240k row scan buys an operator nothing but a temp
        table.
        """
        self._case(self.ovg, "ECLI:DE:VGBE:2018:1220.2K1.17.00", "2 K 1.17")

        with CaptureQueriesContext(connection) as queries:
            self._run()

        scans = [q["sql"] for q in queries if "ecli" in q["sql"].lower()]
        self.assertTrue(scans)
        for sql in scans:
            self.assertNotIn("ORDER BY", sql.upper())

    def test_empty_corpus_does_not_divide_by_zero(self):
        output = self._run()

        self.assertIn("ECLI disagrees with court: 0 (n/a of scanned)", output)
