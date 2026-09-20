"""Tests for the ``reassign_courts_from_ecli`` management command.

The failure shape is the one reported in #256: a first-instance decision
whose ECLI reads ``ECLI:DE:VGBE:…`` sits under Oberverwaltungsgericht
Berlin-Brandenburg, because the OVG's alias line ``OVG Berlin`` matched
the substring ``VG Berlin``. The tests seed that shape directly and
assert the command moves only the rows whose own ECLI names the target
court.
"""

import re
from collections import Counter
from datetime import date
from io import StringIO
from unittest import mock

from django.core.cache import cache
from django.core.management import CommandError, call_command
from django.db import DatabaseError, OperationalError
from django.test import TestCase, override_settings, tag

from oldp.apps.cases.cache import CASE_DATA_KEY
from oldp.apps.cases.management.commands.reassign_courts_from_ecli import Command
from oldp.apps.cases.models import Case
from oldp.apps.courts.models import Country, Court, State
from oldp.apps.search.mock_backend import MockElasticsearchBackend


@tag("commands")
class ReassignCourtsFromEcliTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        country, _ = Country.objects.get_or_create(
            code="DE", defaults={"name": "Germany"}
        )
        state, _ = State.objects.get_or_create(
            pk=1, defaults={"name": "Berlin", "country": country, "slug": "berlin"}
        )
        cls.ovg = Court.objects.create(
            name="Oberverwaltungsgericht Berlin-Brandenburg",
            slug="ovgbebb",
            code="OVGBEBB",
            court_type="OVG",
            state=state,
            aliases="Oberverwaltungsgericht Berlin-Brandenburg\nOVG Berlin",
        )
        cls.vg = Court.objects.create(
            name="Verwaltungsgericht Berlin",
            slug="vg-berlin",
            code="VGBE",
            court_type="VG",
            state=state,
        )
        # The second default pair, same shape: the source court's alias
        # line swallows the target's short name, the target has none.
        cls.olg_rostock = Court.objects.create(
            name="Oberlandesgericht Rostock",
            slug="olg-rostock",
            code="OLGROST",
            court_type="OLG",
            state=state,
            aliases="Oberlandesgericht Rostock\nOLG Rostock",
        )
        cls.lg_rostock = Court.objects.create(
            name="Landgericht Rostock",
            slug="lg-rostock",
            code="LGROSTO",
            court_type="LG",
            state=state,
        )

    def _case(self, file_number, ecli, court=None):
        case = Case(
            court=court or self.ovg,
            file_number=file_number,
            date=date(2018, 12, 20),
            content="<p>Test</p>",
            ecli=ecli,
        )
        case.set_slug()
        case.save()
        return case

    def _run(self, *args, pair="OVGBEBB:VGBE"):
        out = StringIO()
        call_command("reassign_courts_from_ecli", "--pair", pair, *args, stdout=out)
        return out.getvalue()

    # ``  Cases scanned:   3`` -> ("Cases scanned", 3). Parsed rather than
    # matched as a literal so the report's column width stays a formatting
    # detail instead of something every assertion has to agree on.
    COUNTER_LINE = re.compile(r"^ {2}(?P<label>.+?):\s+(?P<count>\d+)$")

    def _sections(self, output):
        """Parse the report into ``{heading: {label: count}}``.

        Headings are the per-pair lines and ``Total``; counter rows are the
        indented lines under them.
        """
        sections, heading = {}, None
        for line in output.splitlines():
            row = self.COUNTER_LINE.match(line)
            if row and heading is not None:
                sections[heading][row["label"]] = int(row["count"])
            elif line.strip():
                heading = line.strip()
                sections.setdefault(heading, {})
        return sections

    def _totals(self, output):
        """Counter rows of the ``Total`` block."""
        return self._sections(output)["Total"]

    def test_case_is_refiled_and_slug_rewritten(self):
        """A VGBE ECLI under the OVG moves to VG Berlin, slug follows."""
        case = self._case("2 K 178.17", "ECLI:DE:VGBE:2018:1220.2K178.17.00")
        old_slug = case.slug

        self._run("--write")

        case.refresh_from_db()
        self.assertEqual(case.court.code, "VGBE")
        self.assertNotEqual(case.slug, old_slug)
        self.assertTrue(case.slug.startswith("vg-berlin-"))

    def test_zero_argument_invocation_runs_every_audited_default(self):
        """The form the runbook tells operators to run, with no ``--pair``.

        Every other test passes its pair explicitly, so nothing else
        exercises ``DEFAULT_PAIRS`` itself. It also holds the line on what
        may become a default: a pair whose courts are not in this fixture
        fails here with "Unknown court code" rather than reaching an
        operator.
        """
        berlin = self._case("2 K 178.17", "ECLI:DE:VGBE:2018:1220.2K178.17.00")
        rostock = self._case(
            "4 O 12/19",
            "ECLI:DE:LGROSTO:2019:0304.4O12.19.00",
            court=self.olg_rostock,
        )

        call_command("reassign_courts_from_ecli", "--write", stdout=StringIO())

        berlin.refresh_from_db()
        rostock.refresh_from_db()
        self.assertEqual(berlin.court.code, "VGBE")
        self.assertEqual(rostock.court.code, "LGROSTO")

    def test_case_whose_ecli_names_the_assigned_court_is_untouched(self):
        """A genuine OVG decision under the OVG must not be moved."""
        case = self._case("OVG 2 N 225/26", "ECLI:DE:OVGBEBB:2026:0811.OVG2N225.26.00")

        self._run("--write")

        case.refresh_from_db()
        self.assertEqual(case.court.code, "OVGBEBB")

    def test_case_without_ecli_is_untouched(self):
        """No ECLI means no deterministic target, so the row is left alone."""
        case = self._case("3 K 1/18", "")

        output = self._run("--write")

        case.refresh_from_db()
        self.assertEqual(case.court.code, "OVGBEBB")
        self.assertEqual(self._totals(output)["Skipped (no usable ECLI)"], 1)

    def test_case_without_file_number_is_skipped(self):
        """A NULL file_number has no slug to derive, so the row is skipped.

        Without the guard this aborts the whole run: ``set_slug`` does
        ``file_number[:20]`` and raises ``TypeError`` on ``None``, leaving
        the cases already re-filed committed and no summary printed.
        """
        case = Case(
            court=self.ovg,
            file_number=None,
            date=date(2018, 12, 20),
            content="<p>Test</p>",
            ecli="ECLI:DE:VGBE:2018:1220.2K179.17.00",
            slug="ovgbebb-2018-12-20-no-file-number",
        )
        case.save()
        survivor = self._case("2 K 178.17", "ECLI:DE:VGBE:2018:1220.2K178.17.00")

        output = self._run("--write")

        case.refresh_from_db()
        survivor.refresh_from_db()
        self.assertEqual(case.court.code, "OVGBEBB")
        self.assertEqual(survivor.court.code, "VGBE")
        self.assertEqual(self._totals(output)["Skipped (no file number)"], 1)

    def test_duplicate_at_target_court_is_skipped(self):
        """unique_together(court, file_number) collisions are left for a human."""
        self._case("2 K 178.17", "ECLI:DE:VGBE:2018:1220.2K178.17.00", court=self.vg)
        stray = self._case("2 K 178.17", "ECLI:DE:VGBE:2018:1220.2K178.17.00")

        output = self._run("--write")

        stray.refresh_from_db()
        self.assertEqual(stray.court.code, "OVGBEBB")
        self.assertEqual(self._totals(output)["Skipped (duplicate at target)"], 1)

    def test_slug_collision_is_reported_without_writing(self):
        """A slug collision is detected before the write, so both modes agree.

        ``set_slug`` truncates ``file_number`` to 20 characters, so two
        distinct file numbers can land on one slug without tripping
        ``unique_together(court, file_number)``. The report is the mode an
        operator sizes the change from, so it has to see this.
        """
        self._case(
            "2 K 178.17 aaaaaaaaaaAAA",
            "ECLI:DE:VGBE:2018:1220.2K178.17.00",
            court=self.vg,
        )
        stray = self._case(
            "2 K 178.17 aaaaaaaaaaBBB", "ECLI:DE:VGBE:2018:1220.2K179.17.00"
        )

        report = self._run()
        written = self._run("--write")

        stray.refresh_from_db()
        self.assertEqual(stray.court.code, "OVGBEBB")
        for output in (report, written):
            totals = self._totals(output)
            self.assertEqual(totals["Cases re-filed"], 0)
            self.assertEqual(totals["Skipped (slug collision)"], 1)
            self.assertEqual(totals["Skipped (write conflict)"], 0)

    def _second_source_court(self):
        """A second court whose cases the ECLI also sends to VG Berlin."""
        return Court.objects.create(
            name="Hamburgisches Oberverwaltungsgericht",
            slug="ovghh",
            code="OVGHH",
            court_type="OVG",
            state=self.ovg.state,
        )

    def _run_two_pairs(self, *args):
        """Run both pairs into VGBE and return the ``Total`` counters."""
        out = StringIO()
        call_command(
            "reassign_courts_from_ecli",
            "--pair",
            "OVGBEBB:VGBE",
            "--pair",
            "OVGHH:VGBE",
            *args,
            stdout=out,
        )
        return self._totals(out.getvalue())

    def test_slug_claimed_earlier_in_the_run_is_reported_as_a_collision(self):
        """The colliding row may be one this same run moved a moment ago.

        Two pairs can name one target court. Until the first row commits,
        the second row's slug is free in the database — so a report that
        only asks the database promises a move the write then skips.
        """
        other = self._second_source_court()
        # Differ only past the 20th character, which is all ``set_slug``
        # keeps, so the two are not duplicates by file number but land on
        # one slug at VGBE. Distinct under their own courts, which is why
        # the unique index lets them exist side by side to begin with.
        self._case("2 K 178.17 aaaaaaaaaaAAA", "ECLI:DE:VGBE:2018:1220.2K178.17.00")
        self._case(
            "2 K 178.17 aaaaaaaaaaBBB",
            "ECLI:DE:VGBE:2018:1220.2K179.17.00",
            court=other,
        )

        report = self._run_two_pairs()
        written = self._run_two_pairs("--write")

        self.assertEqual(Case.objects.filter(court=self.vg).count(), 1)
        for totals in (report, written):
            self.assertEqual(totals["Cases re-filed"], 1)
            self.assertEqual(totals["Skipped (slug collision)"], 1)

    def test_file_number_claimed_earlier_in_the_run_is_reported_as_a_duplicate(self):
        """Same hole in the other pre-check: ``unique_together`` at the target."""
        other = self._second_source_court()
        self._case("2 K 178.17", "ECLI:DE:VGBE:2018:1220.2K178.17.00")
        self._case("2 K 178.17", "ECLI:DE:VGBE:2018:1220.2K178.17.00", court=other)

        report = self._run_two_pairs()
        written = self._run_two_pairs("--write")

        self.assertEqual(Case.objects.filter(court=self.vg).count(), 1)
        for totals in (report, written):
            self.assertEqual(totals["Cases re-filed"], 1)
            self.assertEqual(totals["Skipped (duplicate at target)"], 1)

    def _run_relay(self, *args):
        """Run OVGBEBB -> OVGHH and VGBE -> OVGBEBB, where pair 2 follows pair 1.

        The first pair's source is the second pair's target, so pair 1
        vacates a slug and a file number that pair 2 then wants.
        """
        out = StringIO()
        call_command(
            "reassign_courts_from_ecli",
            "--pair",
            "OVGBEBB:OVGHH",
            "--pair",
            "VGBE:OVGBEBB",
            *args,
            stdout=out,
        )
        return self._totals(out.getvalue())

    def test_slug_freed_earlier_in_the_run_is_not_reported_as_a_collision(self):
        """The row holding the slug may be one this run has already moved.

        A report writes nothing, so the database still shows that row in
        its old place long after the run decided to move it. Counting the
        follower as a collision would understate what the write does.
        """
        other = self._second_source_court()
        # Same slug suffix, different file numbers past the 20th character,
        # so the two compete for a slug and not for a file number.
        self._case("2 K 178.17 aaaaaaaaaaAAA", "ECLI:DE:OVGHH:2018:1220.2K178.17.00")
        self._case(
            "2 K 178.17 aaaaaaaaaaBBB",
            "ECLI:DE:OVGBEBB:2018:1220.2K179.17.00",
            court=self.vg,
        )

        report = self._run_relay()
        written = self._run_relay("--write")

        self.assertEqual(Case.objects.filter(court=other).count(), 1)
        self.assertEqual(Case.objects.filter(court=self.ovg).count(), 1)
        for totals in (report, written):
            self.assertEqual(totals["Cases re-filed"], 2)
            self.assertEqual(totals["Skipped (slug collision)"], 0)

    def test_file_number_freed_earlier_in_the_run_is_not_reported_as_a_duplicate(self):
        """Same for ``unique_together``: the holder may have moved out already."""
        other = self._second_source_court()
        self._case("2 K 178.17", "ECLI:DE:OVGHH:2018:1220.2K178.17.00")
        self._case("2 K 178.17", "ECLI:DE:OVGBEBB:2018:1220.2K178.17.00", court=self.vg)

        report = self._run_relay()
        written = self._run_relay("--write")

        self.assertEqual(Case.objects.filter(court=other).count(), 1)
        self.assertEqual(Case.objects.filter(court=self.ovg).count(), 1)
        for totals in (report, written):
            self.assertEqual(totals["Cases re-filed"], 2)
            self.assertEqual(totals["Skipped (duplicate at target)"], 0)

    def test_writing_requires_the_write_flag(self):
        """Without --write the command reports the move but does not make it.

        The default is the report, so a forgotten flag costs an operator a
        second run rather than six thousand silently moved rows.
        """
        case = self._case("2 K 178.17", "ECLI:DE:VGBE:2018:1220.2K178.17.00")

        output = self._run()

        case.refresh_from_db()
        self.assertEqual(case.court.code, "OVGBEBB")
        self.assertEqual(self._totals(output)["Cases re-filed"], 1)
        self.assertIn("Pass --write to apply.", output)

    def test_limit_counts_cases_moved_not_cases_seen(self):
        """A row that stays put must not spend the limit.

        Most of what the walk sees belongs where it is — 5,163 of the 11,537
        rows under the OVG in the production audit — so counting those would
        make ``--limit`` unusable for sampling.
        """
        self._case("9 K 9.17", "ECLI:DE:OVGBEBB:2018:1220.9K9.17.00")
        self._case("2 K 1.17", "ECLI:DE:VGBE:2018:1220.2K1.17.00")
        self._case("2 K 2.17", "ECLI:DE:VGBE:2018:1220.2K2.17.00")

        output = self._run("--write", "--limit", "1")

        self.assertEqual(Case.objects.filter(court=self.vg).count(), 1)
        self.assertEqual(self._totals(output)["Cases re-filed"], 1)
        # Two rows walked: the one that stayed, then the one that moved.
        self.assertEqual(self._totals(output)["Cases scanned"], 2)

    def test_limit_applies_to_each_pair(self):
        """Per pair, so a big first pair cannot starve the second one."""
        self._case("2 K 1.17", "ECLI:DE:VGBE:2018:1220.2K1.17.00")
        self._case("2 K 2.17", "ECLI:DE:VGBE:2018:1220.2K2.17.00")
        self._case(
            "OVG 1 N 1.26", "ECLI:DE:OVGBEBB:2026:0811.OVG1N1.26.00", court=self.vg
        )
        self._case(
            "OVG 2 N 2.26", "ECLI:DE:OVGBEBB:2026:0811.OVG2N2.26.00", court=self.vg
        )

        out = StringIO()
        call_command(
            "reassign_courts_from_ecli",
            "--pair",
            "OVGBEBB:VGBE",
            "--pair",
            "VGBE:OVGBEBB",
            "--write",
            "--limit",
            "1",
            stdout=out,
        )
        sections = self._sections(out.getvalue())

        for heading, counters in sections.items():
            if heading != "Total":
                self.assertEqual(counters["Cases re-filed"], 1, heading)
        self.assertEqual(sections["Total"]["Cases re-filed"], 2)

    def test_index_is_written_once_in_bulk_not_per_save(self):
        """The per-save ES hook is off during the run; one bulk write instead.

        Per-save indexing would be ~6k sequential round-trips, and the hook
        swallows its own failures — so a flaky index would leave documents
        naming the old court behind a clean report.
        """
        MockElasticsearchBackend.reset()
        self._case("2 K 1.17", "ECLI:DE:VGBE:2018:1220.2K1.17.00")
        self._case("2 K 2.17", "ECLI:DE:VGBE:2018:1220.2K2.17.00")

        with mock.patch(
            "oldp.apps.cases.signals._sync_case_to_search_index"
        ) as per_save:
            # The hook defers to ``transaction.on_commit``, which a TestCase
            # never reaches on its own — without this the assertion below
            # would pass even with the hook connected.
            with self.captureOnCommitCallbacks(execute=True):
                output = self._run("--write")

        per_save.assert_not_called()
        self.assertEqual(self._totals(output)["Documents re-indexed"], 2)
        self.assertEqual(MockElasticsearchBackend.get_document_count(), 2)

    def test_indexed_document_names_the_new_court(self):
        """The court is part of the document, so a missed write breaks search."""
        MockElasticsearchBackend.reset()
        case = self._case("2 K 178.17", "ECLI:DE:VGBE:2018:1220.2K178.17.00")

        self._run("--write")

        case.refresh_from_db()
        documents = list(MockElasticsearchBackend._documents.values())
        self.assertEqual(len(documents), 1)
        self.assertEqual(documents[0]["data"]["court"], "VGBE")
        self.assertEqual(documents[0]["data"]["slug"], case.slug)

    def test_per_save_hook_is_reconnected_afterwards(self):
        """A disconnected hook must not leak into whatever runs next.

        Asserted through behaviour rather than the receiver list: the
        command runs in-process under ``call_command``, so a hook left
        disconnected would silently stop indexing for the rest of the
        process, tests included.
        """
        self._run("--write")

        with mock.patch(
            "oldp.apps.cases.signals._sync_case_to_search_index"
        ) as per_save:
            with self.captureOnCommitCallbacks(execute=True):
                self._case("9 K 9.19", "ECLI:DE:VGBE:2019:0101.9K9.19.00")

        per_save.assert_called_once()

    def test_each_pair_is_reported_separately(self):
        """Per-pair blocks plus a Total, so a bad pair is attributable."""
        self._case("2 K 178.17", "ECLI:DE:VGBE:2018:1220.2K178.17.00")
        self._case("2 K 179.17", "ECLI:DE:OVGBEBB:2018:1220.2K179.17.00")

        out = StringIO()
        call_command(
            "reassign_courts_from_ecli",
            "--pair",
            "OVGBEBB:VGBE",
            "--pair",
            "VGBE:OVGBEBB",
            "--write",
            stdout=out,
        )
        sections = self._sections(out.getvalue())

        forwards = sections[
            "OVGBEBB -> VGBE (Oberverwaltungsgericht Berlin-Brandenburg "
            "-> Verwaltungsgericht Berlin)"
        ]
        backwards = sections[
            "VGBE -> OVGBEBB (Verwaltungsgericht Berlin "
            "-> Oberverwaltungsgericht Berlin-Brandenburg)"
        ]
        self.assertEqual(forwards["Cases re-filed"], 1)
        self.assertEqual(forwards["Skipped (ECLI does not name the target)"], 1)
        # The pair above moved one case into VGBE; it stays there, because
        # its own ECLI names VGBE.
        self.assertEqual(backwards["Cases re-filed"], 0)
        self.assertEqual(sections["Total"]["Cases re-filed"], 1)
        self.assertEqual(sections["Total"]["Cases scanned"], 3)

    def test_pair_direction_is_not_hardcoded(self):
        """An OVG decision filed under the VG moves the other way."""
        case = self._case(
            "OVG 2 N 225.26",
            "ECLI:DE:OVGBEBB:2026:0811.OVG2N225.26.00",
            court=self.vg,
        )

        self._run("--write", pair="VGBE:OVGBEBB")

        case.refresh_from_db()
        self.assertEqual(case.court.code, "OVGBEBB")
        self.assertTrue(case.slug.startswith("ovgbebb-"))

    # ``TestConfiguration`` caches into ``DummyCache``, where every read
    # misses and this assertion would hold with no invalidation at all.
    @override_settings(
        CACHES={
            "default": {
                "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            }
        }
    )
    def test_cached_page_under_the_old_slug_is_dropped(self):
        """The old URL no longer resolves, so its cached page must go.

        ``post_save`` only invalidates the slug the case now has; without
        the explicit call the old key would keep serving a page for an
        address that 404s.
        """
        case = self._case("2 K 178.17", "ECLI:DE:VGBE:2018:1220.2K178.17.00")
        old_slug = case.slug
        cache.set(CASE_DATA_KEY % old_slug, {"stale": True})

        self._run("--write")

        case.refresh_from_db()
        self.assertNotEqual(case.slug, old_slug)
        self.assertIsNone(cache.get(CASE_DATA_KEY % old_slug))

    def test_abort_mid_run_still_indexes_what_was_committed(self):
        """Moves commit as they happen, so an aborted run must still index.

        Otherwise search keeps naming the old court, and linking the old
        slug, for cases that already moved.
        """
        MockElasticsearchBackend.reset()
        self._case("2 K 1.17", "ECLI:DE:VGBE:2018:1220.2K1.17.00")
        self._case("2 K 2.17", "ECLI:DE:VGBE:2018:1220.2K2.17.00")

        with mock.patch(
            "oldp.apps.cases.management.commands."
            "reassign_courts_from_ecli.invalidate_case_cache",
            side_effect=[None, RuntimeError("boom")],
        ):
            with self.assertRaises(RuntimeError):
                self._run("--write")

        self.assertEqual(Case.objects.filter(court=self.vg).count(), 2)
        self.assertEqual(MockElasticsearchBackend.get_document_count(), 2)

    def test_abort_mid_run_reports_what_happened(self):
        """The summary and a resume hint survive the failure."""
        self._case("2 K 1.17", "ECLI:DE:VGBE:2018:1220.2K1.17.00")

        out = StringIO()
        with mock.patch(
            "oldp.apps.cases.management.commands."
            "reassign_courts_from_ecli.invalidate_case_cache",
            side_effect=RuntimeError("boom"),
        ):
            with self.assertRaises(RuntimeError):
                call_command(
                    "reassign_courts_from_ecli",
                    "--pair",
                    "OVGBEBB:VGBE",
                    "--write",
                    stdout=out,
                )

        output = out.getvalue()
        totals = self._totals(output)
        # The row is committed and indexed, so the counters must say so —
        # otherwise the closing line claims zero cases are committed.
        self.assertEqual(totals["Cases scanned"], 1)
        self.assertEqual(totals["Cases re-filed"], 1)
        self.assertEqual(totals["Documents re-indexed"], 1)
        self.assertIn("Run did not finish", output)

    def test_clean_run_is_not_called_aborted_because_the_caller_is_unwinding(self):
        """The abort flag must describe this run, not the caller's stack.

        ``sys.exc_info()`` inside the ``finally`` reports whatever is being
        handled anywhere above, so a command invoked from an ``except``
        block used to report a perfectly complete run as aborted.
        """
        self._case("2 K 1.17", "ECLI:DE:VGBE:2018:1220.2K1.17.00")

        out = StringIO()
        try:
            raise KeyError("the caller's own problem")
        except KeyError:
            call_command(
                "reassign_courts_from_ecli",
                "--pair",
                "OVGBEBB:VGBE",
                "--write",
                stdout=out,
            )

        self.assertNotIn("Run did not finish", out.getvalue())

    def test_indexing_failure_raises_even_while_the_caller_is_unwinding(self):
        """The costly half of the same mistake.

        An index error is printed rather than raised when the run itself
        aborted, so that it cannot mask the original failure. Mistaking
        the caller's exception for our own turned that into an exit code
        of 0 over a search index still naming the old court.
        """
        self._case("2 K 1.17", "ECLI:DE:VGBE:2018:1220.2K1.17.00")

        try:
            raise KeyError("the caller's own problem")
        except KeyError:
            with mock.patch.object(
                MockElasticsearchBackend, "update", side_effect=RuntimeError("es down")
            ):
                with self.assertRaises(CommandError):
                    call_command(
                        "reassign_courts_from_ecli",
                        "--pair",
                        "OVGBEBB:VGBE",
                        "--write",
                        stdout=StringIO(),
                    )

    def test_row_deleted_mid_run_is_a_conflict_not_a_crash(self):
        """A vanished row raises past ``IntegrityError``; it must not abort."""
        self._case("2 K 1.17", "ECLI:DE:VGBE:2018:1220.2K1.17.00")

        with mock.patch.object(
            Case,
            "save",
            side_effect=DatabaseError(
                "Save with update_fields did not affect any rows."
            ),
        ):
            output = self._run("--write")

        totals = self._totals(output)
        self.assertEqual(totals["Skipped (write conflict)"], 1)
        self.assertEqual(totals["Cases re-filed"], 0)

    def test_vanished_row_seen_as_does_not_exist_is_a_conflict(self):
        """``save()`` reads the deferred ``content`` last, so this is the
        other way a concurrent delete surfaces.
        """
        self._case("2 K 1.17", "ECLI:DE:VGBE:2018:1220.2K1.17.00")

        with mock.patch.object(Case, "save", side_effect=Case.DoesNotExist):
            output = self._run("--write")

        self.assertEqual(self._totals(output)["Skipped (write conflict)"], 1)

    def test_broken_database_is_not_swallowed_as_a_conflict(self):
        """A dropped connection must abort, not be counted 6,000 times."""
        self._case("2 K 1.17", "ECLI:DE:VGBE:2018:1220.2K1.17.00")

        with mock.patch.object(
            Case, "save", side_effect=OperationalError("server has gone away")
        ):
            with self.assertRaises(OperationalError):
                self._run("--write")

    def test_documents_written_before_an_index_failure_are_counted(self):
        """A failed batch must not erase the batches that went in before it.

        ``_reindex`` sends the cases in chunks, so a failure can land with
        documents already written. The error message names that count, and
        the summary printed just above it has to agree.
        """
        first = self._case("2 K 1.17", "ECLI:DE:VGBE:2018:1220.2K1.17.00")
        second = self._case("2 K 2.17", "ECLI:DE:VGBE:2018:1220.2K2.17.00")
        totals = Counter()

        with mock.patch.object(
            MockElasticsearchBackend,
            "update",
            side_effect=[None, RuntimeError("es down")],
        ):
            with self.assertRaises(CommandError) as raised:
                Command()._reindex([first.pk, second.pk], totals, batch_size=1)

        self.assertEqual(totals["indexed"], 1)
        self.assertIn("after 1 documents", str(raised.exception))

    def test_summary_survives_an_indexing_failure(self):
        """Counters describe committed rows, so they outlive a broken index."""
        self._case("2 K 1.17", "ECLI:DE:VGBE:2018:1220.2K1.17.00")

        out = StringIO()
        with mock.patch.object(
            MockElasticsearchBackend, "update", side_effect=RuntimeError("es down")
        ):
            with self.assertRaises(CommandError) as raised:
                call_command(
                    "reassign_courts_from_ecli",
                    "--pair",
                    "OVGBEBB:VGBE",
                    "--write",
                    stdout=out,
                )

        self.assertIn("update_index cases", str(raised.exception))
        self.assertEqual(self._totals(out.getvalue())["Cases re-filed"], 1)

    def test_indexing_failure_does_not_mask_the_original_one(self):
        """While unwinding, the index error is printed, never raised."""
        self._case("2 K 1.17", "ECLI:DE:VGBE:2018:1220.2K1.17.00")

        out = StringIO()
        with mock.patch(
            "oldp.apps.cases.management.commands."
            "reassign_courts_from_ecli.invalidate_case_cache",
            side_effect=RuntimeError("the actual failure"),
        ):
            with mock.patch.object(
                MockElasticsearchBackend, "update", side_effect=RuntimeError("es down")
            ):
                with self.assertRaises(RuntimeError) as raised:
                    call_command(
                        "reassign_courts_from_ecli",
                        "--pair",
                        "OVGBEBB:VGBE",
                        "--write",
                        stdout=out,
                    )

        self.assertEqual(str(raised.exception), "the actual failure")
        self.assertIn("update_index cases", out.getvalue())

    def test_aborted_report_does_not_claim_the_counted_cases_are_committed(self):
        """A report commits nothing, so the abort line cannot say it did.

        The two closing lines land one after the other: "no rows were
        written" and, without this, "the cases counted above are
        committed".
        """
        self._case("2 K 1.17", "ECLI:DE:VGBE:2018:1220.2K1.17.00")

        out = StringIO()
        with mock.patch(
            "oldp.apps.cases.management.commands."
            "reassign_courts_from_ecli.court_code_from_ecli",
            side_effect=RuntimeError("boom"),
        ):
            with self.assertRaises(RuntimeError):
                call_command(
                    "reassign_courts_from_ecli",
                    "--pair",
                    "OVGBEBB:VGBE",
                    stdout=out,
                )

        output = out.getvalue()
        self.assertIn("Run did not finish", output)
        self.assertIn("Nothing was written", output)
        self.assertNotIn("are committed", output)

    def test_abort_and_index_failure_get_an_order_not_two_contradictions(self):
        """Each closing line is right alone; together they disagree.

        "re-running resumes from what is left" and "do not re-run this
        command" cannot both be followed. A re-run is what moves the rows
        the abort left behind, but it cannot repair the index: the rows
        already moved are no longer under the source court, so the walk
        never hands them to the bulk pass again.

        Both contradicting sentences are asserted absent. One was a line
        of its own; the other was inside the text of the indexing error,
        which is printed either way.
        """
        self._case("2 K 1.17", "ECLI:DE:VGBE:2018:1220.2K1.17.00")

        out = StringIO()
        with mock.patch(
            "oldp.apps.cases.management.commands."
            "reassign_courts_from_ecli.invalidate_case_cache",
            side_effect=RuntimeError("the actual failure"),
        ):
            with mock.patch.object(
                MockElasticsearchBackend, "update", side_effect=RuntimeError("es down")
            ):
                with self.assertRaises(RuntimeError):
                    call_command(
                        "reassign_courts_from_ecli",
                        "--pair",
                        "OVGBEBB:VGBE",
                        "--write",
                        stdout=out,
                    )

        output = out.getvalue()
        self.assertIn("update_index cases", output)
        self.assertIn("then re-run this command", output)
        # Both halves of the contradiction, not just the one that used to
        # be printed as its own line: the other lived inside the indexing
        # error's own text.
        self.assertNotIn("re-running resumes from what is left", output)
        self.assertNotIn("do not re-run this command", output)

    def test_negative_limit_is_rejected(self):
        """Not silently a no-op: ``0 >= -1`` would break on the first row.

        The command would then exit 0 with an all-zeros report and the
        reassuring "no rows were written" line — a typo reading as "there
        is nothing to repair".
        """
        self._case("2 K 1.17", "ECLI:DE:VGBE:2018:1220.2K1.17.00")

        with self.assertRaises(CommandError):
            self._run("--limit", "-1")

    def test_malformed_pair_raises(self):
        with self.assertRaises(CommandError):
            call_command("reassign_courts_from_ecli", "--pair", "OVGBEBB")

    def test_ambiguous_court_code_raises(self):
        """``code`` is unique, but not past case on every collation.

        The pair lookup matches case-insensitively on purpose, so it can
        find two rows where the unique index sees two distinct codes. That
        has to be a ``CommandError`` like any other bad pair, not a
        ``MultipleObjectsReturned`` traceback.
        """
        Court.objects.create(
            name="Verwaltungsgericht Berlin (duplicate row)",
            slug="vg-berlin-duplicate",
            code="vgbe",
            court_type="VG",
            state=self.ovg.state,
        )

        with self.assertRaises(CommandError):
            call_command("reassign_courts_from_ecli", "--pair", "OVGBEBB:VGBE")

    def test_unknown_court_code_raises(self):
        with self.assertRaises(CommandError):
            call_command("reassign_courts_from_ecli", "--pair", "OVGBEBB:NOSUCH")
