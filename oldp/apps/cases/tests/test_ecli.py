"""Tests for the ECLI sanity checks and the ``repair_case_eclis`` command.

The examples are the misattributions reported in #255 and found on prod,
plus correct ECLIs in every format the check has to tolerate.
"""

from datetime import date
from io import StringIO

from django.core.management import call_command
from django.test import SimpleTestCase, TestCase, tag

from oldp.apps.cases.ecli import (
    ecli_contradicts_case,
    normalize_ecli,
    parse_ecli,
)
from oldp.apps.cases.models import Case
from oldp.apps.cases.services import CaseCreator
from oldp.apps.courts.models import Country, Court, State


class NormalizeEcliTestCase(SimpleTestCase):
    def test_repeated_prefix_is_collapsed(self):
        self.assertEqual(
            normalize_ecli("ECLI:ECLI:DE:VGWIESB:2019:0329.3L2332.17.00"),
            "ECLI:DE:VGWIESB:2019:0329.3L2332.17.00",
        )

    def test_blank_and_none(self):
        self.assertEqual(normalize_ecli(None), "")
        self.assertEqual(normalize_ecli("  "), "")

    def test_parse_splits_court_date_and_docket(self):
        self.assertEqual(
            parse_ecli("ECLI:DE:VGBE:2018:0221.VG18L43.18.00"),
            ("VGBE", date(2018, 2, 21), "VG18L43.18.00"),
        )
        self.assertIsNone(parse_ecli("ECLI:EU:C:2019:1"))


class EcliContradictsCaseTestCase(SimpleTestCase):
    def test_correct_eclis_in_every_format_are_accepted(self):
        for ecli, file_number, day in [
            # Länder, MMDD + docket
            ("ECLI:DE:VGBE:2018:0507.VG34L73.18A.00", "34 L73.18 A", "2018-05-07"),
            # BVerfG pads the numbers
            ("ECLI:DE:BVerfG:2020:rk20201208.1bvr011716", "1 BvR 117/16", "2020-12-08"),
            # Federal courts, DDMMYY + kind
            ("ECLI:DE:BGH:2015:261115B2STR144.15.0", "2 StR 144/15", "2015-11-26"),
            # BSG glues number and year
            ("ECLI:DE:BSG:2019:080819UB3KR2118R3", "B 3 KR 21/18 R", "2019-08-08"),
            # Register number in front (Thüringen)
            ("ECLI:DE:LGMEINI:2021:0517.4T85.21.00", "(13) 4 T 85/21", "2021-05-19"),
            # Truncated ECLI of a long NRW file number
            (
                "ECLI:DE:LGDU:2014:0429.34KLS143JS193.10.00",
                "34 KLs-143 Js 193/10-15/13",
                "2014-04-29",
            ),
        ]:
            with self.subTest(ecli=ecli):
                self.assertFalse(ecli_contradicts_case(ecli, file_number, day))

    def test_other_decisions_ecli_is_detected(self):
        for ecli, file_number, day in [
            # Berlin portal swap
            ("ECLI:DE:VGBE:2018:0221.VG18L43.18.00", "34 L73.18 A", "2018-05-07"),
            # NI-VORIS: another state's court
            ("ECLI:DE:LGKIEL:2024:0404.13O40.23.00", "6 O 134/22", "2023-07-27"),
            ("ECLI:DE:SGMAGDE:2023:0703.S6R283.22.00", "10 A 1254/23", "2024-07-25"),
            # Hessen
            ("ECLI:DE:FGHE:2017:1026.1V1165.17.00", "3 K 717/15.DA", "2017-08-21"),
        ]:
            with self.subTest(ecli=ecli):
                self.assertTrue(ecli_contradicts_case(ecli, file_number, day))

    def test_same_day_different_docket_is_not_enough(self):
        """A date match keeps the ECLI: dockets are formatted too freely."""
        self.assertFalse(
            ecli_contradicts_case(
                "ECLI:DE:KG:2020:0226.3SS11.20.00",
                "(3) 161 Ss 8/20 (11/20)",
                "2020-02-26",
            )
        )

    def test_wrong_year_alone_is_not_enough(self):
        self.assertFalse(
            ecli_contradicts_case(
                "ECLI:DE:VGHBW:2024:1030.A13S1907.25.00", "A 13 S 1907/24", "2025-10-30"
            )
        )

    def test_undecidable_input_is_not_a_contradiction(self):
        self.assertFalse(ecli_contradicts_case("", "1 K 1/20", "2020-01-01"))
        self.assertFalse(
            ecli_contradicts_case("ECLI:EU:C:2019:1", "C-1/19", "2019-01-01")
        )
        self.assertFalse(
            ecli_contradicts_case(
                "ECLI:DE:VGBE:2018:0221.VG18L43.18.00", "", "2018-05-07"
            )
        )
        self.assertFalse(
            ecli_contradicts_case(
                "ECLI:DE:VGBE:2018:0221.VG18L43.18.00", "34 L73.18 A", None
            )
        )


class _CasesMixin:
    @classmethod
    def setUpTestData(cls):
        country, _ = Country.objects.get_or_create(
            code="DE", defaults={"name": "Germany"}
        )
        state, _ = State.objects.get_or_create(
            pk=1, defaults={"name": "Berlin", "country": country, "slug": "berlin"}
        )
        cls.vg = Court.objects.create(
            name="Verwaltungsgericht Berlin",
            slug="vg-berlin",
            code="VGBE",
            court_type="VG",
            state=state,
            aliases="Verwaltungsgericht Berlin\nVG Berlin",
        )

    def _case(self, file_number, day, ecli):
        case = Case(
            court=self.vg,
            file_number=file_number,
            date=day,
            content="<p>Test</p>",
            ecli=ecli,
        )
        case.set_slug()
        case.save()
        return case


class CaseCreatorEcliTestCase(_CasesMixin, TestCase):
    def _create(self, ecli, file_number="34 L73.18 A", day=date(2018, 5, 7)):
        return CaseCreator(extract_refs=False).create_case(
            court_name="Verwaltungsgericht Berlin",
            file_number=file_number,
            date=day,
            content="<p>Test</p>",
            ecli=ecli,
        )

    def test_contradicting_ecli_is_dropped(self):
        case = self._create("ECLI:DE:VGBE:2018:0221.VG18L43.18.00")
        self.assertEqual(case.ecli, "")

    def test_correct_ecli_is_kept_and_prefix_collapsed(self):
        case = self._create("ECLI:ECLI:DE:VGBE:2018:0507.VG34L73.18A.00")
        self.assertEqual(case.ecli, "ECLI:DE:VGBE:2018:0507.VG34L73.18A.00")


@tag("commands")
class RepairCaseEclisTestCase(_CasesMixin, TestCase):
    def _run(self, *args):
        out = StringIO()
        call_command("repair_case_eclis", *args, stdout=out)
        return out.getvalue()

    def _swapped_pair(self):
        """The Berlin portal swap: each case carries the other's ECLI."""
        a = self._case(
            "34 L73.18 A", date(2018, 5, 7), "ECLI:DE:VGBE:2018:0221.VG18L43.18.00"
        )
        b = self._case(
            "18 L 43.18", date(2018, 2, 21), "ECLI:DE:VGBE:2018:0507.VG34L73.18A.00"
        )
        return a, b

    def test_report_writes_nothing(self):
        a, b = self._swapped_pair()
        output = self._run()
        a.refresh_from_db()
        self.assertEqual(a.ecli, "ECLI:DE:VGBE:2018:0221.VG18L43.18.00")
        self.assertRegex(output, r"Wrong ECLI cleared \(owner found\):\s+2\b")
        self.assertRegex(output, r"Cleared ECLI given to its owner:\s+2\b")
        self.assertIn("Report only", output)

    def test_swapped_pair_is_put_back(self):
        """Both sides are cleared, then each owner gets its own ECLI back."""
        a, b = self._swapped_pair()
        old_slug, old_updated = a.slug, a.updated_date
        output = self._run("--write")
        a.refresh_from_db()
        b.refresh_from_db()
        self.assertEqual(a.ecli, "ECLI:DE:VGBE:2018:0507.VG34L73.18A.00")
        self.assertEqual(b.ecli, "ECLI:DE:VGBE:2018:0221.VG18L43.18.00")
        self.assertEqual(a.slug, old_slug)
        self.assertEqual(a.updated_date, old_updated)
        self.assertRegex(output, r"Cleared ECLI given to its owner:\s+2\b")

    def test_owner_with_its_own_ecli_keeps_it(self):
        """The duplicate shape: the owner already carries the ECLI."""
        wrong = self._case(
            "34 L73.18 A", date(2018, 5, 7), "ECLI:DE:VGBE:2018:0221.VG18L43.18.00"
        )
        owner = self._case(
            "18 L 43.18", date(2018, 2, 21), "ECLI:DE:VGBE:2018:0221.VG18L43.18.00"
        )
        self._run("--write")
        wrong.refresh_from_db()
        owner.refresh_from_db()
        self.assertEqual(wrong.ecli, "")
        self.assertEqual(owner.ecli, "ECLI:DE:VGBE:2018:0221.VG18L43.18.00")

    def test_wrong_ecli_without_owner_is_kept(self):
        a = self._case(
            "34 L73.18 A", date(2018, 5, 7), "ECLI:DE:VGBE:2018:0221.VG18L43.18.00"
        )
        output = self._run("--write")
        a.refresh_from_db()
        self.assertEqual(a.ecli, "ECLI:DE:VGBE:2018:0221.VG18L43.18.00")
        self.assertRegex(output, r"Wrong ECLI kept \(no owner found\):\s+1\b")

    def test_repeated_prefix_is_collapsed(self):
        a = self._case(
            "3 L 2332/17", date(2019, 3, 29), "ECLI:ECLI:DE:VGBE:2019:0329.3L2332.17.00"
        )
        self._run("--write")
        a.refresh_from_db()
        self.assertEqual(a.ecli, "ECLI:DE:VGBE:2019:0329.3L2332.17.00")

    def test_correct_ecli_is_untouched(self):
        a = self._case(
            "34 L73.18 A", date(2018, 5, 7), "ECLI:DE:VGBE:2018:0507.VG34L73.18A.00"
        )
        output = self._run("--write")
        a.refresh_from_db()
        self.assertEqual(a.ecli, "ECLI:DE:VGBE:2018:0507.VG34L73.18A.00")
        self.assertIn("Repeated prefix collapsed:", output)
