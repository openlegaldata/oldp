from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase, tag

from oldp.apps.accounts.models import APIToken
from oldp.apps.cases.models import Case
from oldp.apps.courts.models import Court


@tag("commands")
class CasesCommandsTestCase(TestCase):
    fixtures = [
        "locations/countries.json",
        "locations/states.json",
        "locations/cities.json",
        "courts/courts.json",
        "cases/cases.json",
    ]

    def setUp(self):
        pass

    def tearDown(self):
        pass

    def test_process_cases_from_db(self):
        call_command(
            "process_cases",
            *["extract_refs", "assign_court"],
            **{"limit": 1, "start": 0, "input_handler": "db"},
        )

    # def test_process_cases_save_fs(self):
    #     call_command('process_cases',
    #                  *['assign_topics', 'extract_refs', 'assign_court'],
    #                  **{'limit': 10, 'start': 1, 'input_handler': 'db'})

    # self.assertEqual(Court.objects.all().count(), 10, 'Invalid court count')


@tag("commands")
class BulkApproveCasesTestCase(TestCase):
    fixtures = [
        "locations/countries.json",
        "locations/states.json",
        "locations/cities.json",
        "courts/courts.json",
        "cases/cases.json",
    ]

    def _pending_count(self):
        return Case.objects.filter(review_status="pending").count()

    def _accepted_count(self):
        return Case.objects.filter(review_status="accepted").count()

    def test_approve_all_pending(self):
        """All pending cases are approved."""
        self.assertEqual(self._pending_count(), 1)
        call_command("bulk_approve_cases")
        self.assertEqual(self._pending_count(), 0)
        self.assertEqual(self._accepted_count(), 3)

    def test_dry_run_does_not_modify(self):
        """Dry run reports count but changes nothing."""
        pending_before = self._pending_count()
        call_command("bulk_approve_cases", "--dry-run")
        self.assertEqual(self._pending_count(), pending_before)

    def test_no_pending_cases(self):
        """Command handles zero pending cases gracefully."""
        Case.objects.filter(review_status="pending").update(review_status="accepted")
        call_command("bulk_approve_cases")
        self.assertEqual(self._pending_count(), 0)

    def test_filter_by_state(self):
        """--state filters by court state ID."""
        # Case pk=2 is pending, court=1 (state=1)
        # Using a non-matching state should leave it pending
        call_command("bulk_approve_cases", "--state", "999")
        self.assertEqual(self._pending_count(), 1)

        # Matching state should approve it
        call_command("bulk_approve_cases", "--state", "1")
        self.assertEqual(self._pending_count(), 0)

    def test_filter_by_date_after(self):
        """--date-after filters cases on or after the given date."""
        # Case pk=2 is pending with date=2018-04-10
        call_command("bulk_approve_cases", "--date-after", "2020-01-01")
        self.assertEqual(self._pending_count(), 1)

        call_command("bulk_approve_cases", "--date-after", "2018-04-10")
        self.assertEqual(self._pending_count(), 0)

    def test_filter_by_date_before(self):
        """--date-before filters cases on or before the given date."""
        # Case pk=2 is pending with date=2018-04-10
        call_command("bulk_approve_cases", "--date-before", "2017-01-01")
        self.assertEqual(self._pending_count(), 1)

        call_command("bulk_approve_cases", "--date-before", "2018-04-10")
        self.assertEqual(self._pending_count(), 0)

    def test_filter_by_date_range(self):
        """Combined --date-after and --date-before narrows the window."""
        call_command(
            "bulk_approve_cases",
            "--date-after", "2018-01-01",
            "--date-before", "2018-12-31",
        )
        self.assertEqual(self._pending_count(), 0)

    def test_filter_by_date_range_miss(self):
        """Date range that excludes the pending case leaves it untouched."""
        call_command(
            "bulk_approve_cases",
            "--date-after", "2019-01-01",
            "--date-before", "2019-12-31",
        )
        self.assertEqual(self._pending_count(), 1)

    def test_filter_by_token(self):
        """--token filters by created_by_token_id."""
        user = get_user_model().objects.create_user("testuser", password="testpass")
        token = APIToken.objects.create(user=user, name="test")
        Case.objects.filter(pk=2).update(created_by_token=token)

        # Non-matching token leaves case pending
        call_command("bulk_approve_cases", "--token", "99999")
        self.assertEqual(self._pending_count(), 1)

        # Matching token approves it
        call_command("bulk_approve_cases", "--token", str(token.pk))
        self.assertEqual(self._pending_count(), 0)

    def test_batch_size(self):
        """--batch-size controls how many cases are updated per batch."""
        # Create extra pending cases so we need multiple batches
        court = Court.objects.get(pk=1)
        for i in range(5):
            Case.objects.create(
                slug=f"batch-test-{i}",
                court=court,
                file_number=f"BATCH/{i}",
                date="2020-01-01",
                content="test",
                review_status="pending",
            )
        self.assertEqual(self._pending_count(), 6)  # 1 from fixture + 5 new

        call_command("bulk_approve_cases", "--batch-size", "2")
        self.assertEqual(self._pending_count(), 0)

    def test_combined_filters(self):
        """Multiple filters are applied together (AND logic)."""
        # Case pk=2: pending, court=1 (state=1), date=2018-04-10
        # State matches but date range doesn't
        call_command(
            "bulk_approve_cases",
            "--state", "1",
            "--date-after", "2020-01-01",
        )
        self.assertEqual(self._pending_count(), 1)

    def test_only_pending_are_affected(self):
        """Accepted and rejected cases are never modified."""
        Case.objects.filter(pk=3).update(review_status="rejected")
        call_command("bulk_approve_cases")
        # pk=2 (pending -> accepted), pk=3 should remain rejected
        self.assertEqual(Case.objects.get(pk=3).review_status, "rejected")
        self.assertEqual(Case.objects.get(pk=2).review_status, "accepted")

    @patch(
        "oldp.apps.cases.management.commands.bulk_approve_cases.Command._update_search_index"
    )
    def test_update_index_called(self, mock_update):
        """--update-index triggers search index updates."""
        call_command("bulk_approve_cases", "--update-index")
        mock_update.assert_called()
        # The call should include the batch of approved case IDs
        call_args = mock_update.call_args[0][0]
        self.assertIn(2, call_args)

    @patch(
        "oldp.apps.cases.management.commands.bulk_approve_cases.Command._update_search_index"
    )
    def test_update_index_not_called_by_default(self, mock_update):
        """Search index is not updated unless --update-index is passed."""
        call_command("bulk_approve_cases")
        mock_update.assert_not_called()

    @patch(
        "oldp.apps.cases.management.commands.bulk_approve_cases.Command._update_search_index"
    )
    def test_update_index_not_called_on_dry_run(self, mock_update):
        """Dry run does not trigger index updates even with --update-index."""
        call_command("bulk_approve_cases", "--dry-run", "--update-index")
        mock_update.assert_not_called()
