"""Tests for ``sync_case_to_search_index_on_save`` signal handler.

Saves and hard-deletes of ``Case`` rows must mirror into ES via the
``CaseIndex`` so the index does not drift when ``review_status``
transitions away from ``accepted``. Without these signals the only
reconciliation path was ``scripts/prune_stale_es_docs.sh``.

The sync is deferred via ``transaction.on_commit`` so each test wraps
its action in ``captureOnCommitCallbacks(execute=True)`` to run those
callbacks in the test transaction.
"""

from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase, TestCase

from oldp.apps.cases.models import Case
from oldp.apps.cases.search_indexes import CaseIndex
from oldp.apps.courts.models import Court


class CaseExactMatchesTestCase(SimpleTestCase):
    """``CaseIndex.exact_matches`` must carry the case's navigational
    handles (file number + ECLI) so a file-number lookup — including the
    ``/search/?q=<file_number>&from=ref`` link rendered for an unresolved
    case citation — ranks the cited case first. The body text does not
    reliably contain the case's own file number, so this is the only
    field that makes the lookup resolve.
    """

    def test_file_number_and_ecli_present(self):
        obj = SimpleNamespace(file_number="VI ZR 123/22", ecli="ECLI:DE:BGH:2022:X")
        forms = CaseIndex().prepare_exact_matches(obj)
        self.assertIn("VI ZR 123/22", forms)
        # Whitespace-free variant for "VIZR123/22"-style pastes.
        self.assertIn("VIZR123/22", forms)
        self.assertIn("ECLI:DE:BGH:2022:X", forms)

    def test_no_blank_entries_when_fields_empty(self):
        obj = SimpleNamespace(file_number="", ecli="")
        self.assertEqual(CaseIndex().prepare_exact_matches(obj), [])

    def test_no_duplicate_when_file_number_has_no_spaces(self):
        obj = SimpleNamespace(file_number="T-345/26", ecli="")
        self.assertEqual(CaseIndex().prepare_exact_matches(obj), ["T-345/26"])


class SyncCaseToSearchIndexTestCase(TestCase):
    fixtures = [
        "locations/countries.json",
        "locations/cities.json",
        "locations/states.json",
        "courts/courts.json",
    ]

    def setUp(self):
        self.court = Court.objects.first()

    def _make_case(self, **overrides):
        kwargs = dict(
            court=self.court,
            file_number="X 1/24",
            date="2024-01-01",
            content="<p>case body</p>",
            review_status="accepted",
        )
        kwargs.update(overrides)
        return Case.objects.create(**kwargs)

    def test_save_accepted_calls_update_object(self):
        with (
            patch(
                "oldp.apps.cases.search_indexes.CaseIndex.update_object"
            ) as mock_update,
            patch(
                "oldp.apps.cases.search_indexes.CaseIndex.remove_object"
            ) as mock_remove,
            self.captureOnCommitCallbacks(execute=True),
        ):
            case = self._make_case(review_status="accepted")
        mock_update.assert_called()
        mock_remove.assert_not_called()
        called_with_instance = mock_update.call_args.args[0]
        self.assertEqual(called_with_instance.pk, case.pk)

    def test_save_pending_calls_remove_object(self):
        with (
            patch(
                "oldp.apps.cases.search_indexes.CaseIndex.update_object"
            ) as mock_update,
            patch(
                "oldp.apps.cases.search_indexes.CaseIndex.remove_object"
            ) as mock_remove,
            self.captureOnCommitCallbacks(execute=True),
        ):
            self._make_case(review_status="pending")
        mock_remove.assert_called()
        mock_update.assert_not_called()

    def test_save_rejected_calls_remove_object(self):
        with (
            patch(
                "oldp.apps.cases.search_indexes.CaseIndex.update_object"
            ) as mock_update,
            patch(
                "oldp.apps.cases.search_indexes.CaseIndex.remove_object"
            ) as mock_remove,
            self.captureOnCommitCallbacks(execute=True),
        ):
            self._make_case(review_status="rejected")
        mock_remove.assert_called()
        mock_update.assert_not_called()

    def test_transition_accepted_to_pending_removes_from_index(self):
        with self.captureOnCommitCallbacks(execute=True):
            case = self._make_case(review_status="accepted")
        with (
            patch(
                "oldp.apps.cases.search_indexes.CaseIndex.update_object"
            ) as mock_update,
            patch(
                "oldp.apps.cases.search_indexes.CaseIndex.remove_object"
            ) as mock_remove,
            self.captureOnCommitCallbacks(execute=True),
        ):
            case.review_status = "pending"
            case.save()
        mock_remove.assert_called()
        mock_update.assert_not_called()

    def test_transition_pending_to_accepted_adds_to_index(self):
        with self.captureOnCommitCallbacks(execute=True):
            case = self._make_case(review_status="pending")
        with (
            patch(
                "oldp.apps.cases.search_indexes.CaseIndex.update_object"
            ) as mock_update,
            patch(
                "oldp.apps.cases.search_indexes.CaseIndex.remove_object"
            ) as mock_remove,
            self.captureOnCommitCallbacks(execute=True),
        ):
            case.review_status = "accepted"
            case.save()
        mock_update.assert_called()
        mock_remove.assert_not_called()

    def test_hard_delete_removes_from_index(self):
        with self.captureOnCommitCallbacks(execute=True):
            case = self._make_case(review_status="accepted")
        with (
            patch(
                "oldp.apps.cases.search_indexes.CaseIndex.remove_object"
            ) as mock_remove,
            self.captureOnCommitCallbacks(execute=True),
        ):
            case.delete()
        mock_remove.assert_called()

    def test_raw_save_skips_sync(self):
        """Loading fixtures (``raw=True``) bypasses ES — deploy pipeline
        runs an explicit ``update_index`` after ``loaddata``.
        """
        from oldp.apps.cases.signals import sync_case_to_search_index_on_save

        with self.captureOnCommitCallbacks(execute=True):
            case = self._make_case(review_status="accepted")
        with (
            patch(
                "oldp.apps.cases.search_indexes.CaseIndex.update_object"
            ) as mock_update,
            patch(
                "oldp.apps.cases.search_indexes.CaseIndex.remove_object"
            ) as mock_remove,
            self.captureOnCommitCallbacks(execute=True),
        ):
            sync_case_to_search_index_on_save(sender=Case, instance=case, raw=True)
        mock_update.assert_not_called()
        mock_remove.assert_not_called()
