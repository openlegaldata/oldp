import os
from datetime import date
from io import StringIO

from django.core.management import call_command
from django.test import TransactionTestCase, tag

from oldp.apps.laws.models import Law, LawBook
from oldp.utils.test_utils import web_test

RESOURCE_DIR = os.path.join(os.path.dirname(os.path.realpath(__file__)), "resources")


@tag("commands")
class LawsCommandsTestCase(TransactionTestCase):
    fixtures = [
        "laws/laws.json",
    ]

    def test_process_laws_from_fs(self):
        call_command(
            "process_laws",
            *[],
            **{
                "limit": 10,
                "start": 1,
                "input_handler": "fs",
                "empty": True,
                "input": os.path.join(RESOURCE_DIR, "from_bundesgit"),
            },
        )

        self.assertEqual(
            96, Law.objects.exclude(book__slug="gg").count(), "Invalid count"
        )

    def test_process_laws_from_db(self):
        call_command(
            "process_laws",
            *["extract_refs"],
            **{"limit": 10, "start": 1, "input_handler": "db"},
        )
        pass

    # def test_process_cases_save_fs(self):
    #     call_command('process_cases',
    #                  *['assign_topics', 'extract_refs', 'assign_court'],
    #                  **{'limit': 10, 'start': 1, 'input_handler': 'db'})

    # self.assertEqual(Court.objects.all().count(), 10, 'Invalid court count')

    @web_test
    def test_import_grundgesetz(self):
        call_command("import_grundgesetz", *[], **{"limit": 2, "empty": True})

    def test_set_law_book_revision(self):
        call_command("set_law_book_revision", *[], **{})

    def test_set_law_book_order(self):
        call_command("set_law_book_order", *[], **{})

    def _seed_two_gg_with_latest_true(self):
        """Bypass clean()/unique_together and force the duplicate state we want
        to repair. Returns the two gg pks (newer first).
        """
        # Clear all latest flags first so we control the exact state.
        LawBook.objects.filter(slug="gg").update(latest=False)
        gg = list(LawBook.objects.filter(slug="gg").order_by("-pk"))
        LawBook.objects.filter(pk__in=[gg[0].pk, gg[1].pk]).update(latest=True)
        return gg[0].pk, gg[1].pk

    def test_dedupe_latest_books_no_duplicates(self):
        out = StringIO()
        call_command("dedupe_latest_books", stdout=out)
        self.assertIn("No duplicate", out.getvalue())

    def test_dedupe_latest_books_resolves_duplicates(self):
        keeper_pk, loser_pk = self._seed_two_gg_with_latest_true()
        self.assertEqual(LawBook.objects.filter(slug="gg", latest=True).count(), 2)

        out = StringIO()
        call_command("dedupe_latest_books", stdout=out)

        latest_rows = LawBook.objects.filter(slug="gg", latest=True)
        self.assertEqual(latest_rows.count(), 1)
        # Keeper is the row with the highest revision_date (and pk tiebreak).
        expected_pk = (
            LawBook.objects.filter(slug="gg", pk__in=[keeper_pk, loser_pk])
            .order_by("-revision_date", "-pk")
            .first()
            .pk
        )
        self.assertEqual(latest_rows.first().pk, expected_pk)
        self.assertIn("Unset latest on 1", out.getvalue())

    def test_dedupe_latest_books_dry_run(self):
        self._seed_two_gg_with_latest_true()
        self.assertEqual(LawBook.objects.filter(slug="gg", latest=True).count(), 2)

        out = StringIO()
        call_command("dedupe_latest_books", "--dry-run", stdout=out)

        # Dry run must leave both latest=True rows intact.
        self.assertEqual(LawBook.objects.filter(slug="gg", latest=True).count(), 2)
        self.assertIn("Dry run", out.getvalue())

    def test_backfill_latest_books_nothing_to_do(self):
        out = StringIO()
        call_command("backfill_latest_books", stdout=out)
        self.assertIn("No books missing", out.getvalue())

    def test_backfill_latest_books_flags_newest(self):
        """A code with revisions but no latest=True gets its newest flagged."""
        # Simulate the broken state for Grundgesetz: no latest at all.
        LawBook.objects.filter(code="Grundgesetz").update(latest=False)
        self.assertEqual(
            LawBook.objects.filter(code="Grundgesetz", latest=True).count(), 0
        )

        out = StringIO()
        call_command("backfill_latest_books", stdout=out)

        latest_rows = LawBook.objects.filter(code="Grundgesetz", latest=True)
        self.assertEqual(latest_rows.count(), 1)
        # The flagged row is the newest revision_date (tiebreak: highest pk).
        expected_pk = (
            LawBook.objects.filter(code="Grundgesetz")
            .order_by("-revision_date", "-pk")
            .first()
            .pk
        )
        self.assertEqual(latest_rows.first().pk, expected_pk)
        self.assertIn("Set latest=True on 1", out.getvalue())

    def test_backfill_latest_books_dry_run(self):
        LawBook.objects.filter(code="Grundgesetz").update(latest=False)

        out = StringIO()
        call_command("backfill_latest_books", "--dry-run", stdout=out)

        # Dry run must leave the broken state untouched.
        self.assertEqual(
            LawBook.objects.filter(code="Grundgesetz", latest=True).count(), 0
        )
        self.assertIn("Dry run", out.getvalue())

    def test_backfill_latest_books_repairs_pending_holding_latest(self):
        """Repairs the root-cause state: a pending revision holds latest while
        the published (accepted) revision does not.
        """
        # Strip the flag from the accepted revisions and let a newer *pending*
        # revision wrongly hold latest=True (the exact bug state).
        LawBook.objects.filter(slug="gg").update(latest=False)
        pending = LawBook.objects.create(
            code="Grundgesetz",
            title="GG pending",
            slug="gg",
            revision_date=date(2020, 1, 1),
            latest=True,
            review_status="pending",
        )

        out = StringIO()
        call_command("backfill_latest_books", stdout=out)

        # latest must land on the newest *accepted* revision, not the pending one.
        accepted_newest = (
            LawBook.objects.filter(slug="gg", review_status="accepted")
            .order_by("-revision_date", "-pk")
            .first()
        )
        self.assertTrue(LawBook.objects.get(pk=accepted_newest.pk).latest)
        self.assertFalse(LawBook.objects.get(pk=pending.pk).latest)
        self.assertEqual(LawBook.objects.filter(slug="gg", latest=True).count(), 1)
