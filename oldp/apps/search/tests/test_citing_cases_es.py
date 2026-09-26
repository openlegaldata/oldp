"""Tests for ``citing_cases_queryset_via_es`` id resolution."""

from unittest.mock import patch

from django.test import TestCase

from oldp.apps.search.mock_backend import MockElasticsearchBackend
from oldp.apps.search.utils import citing_cases_queryset_via_es


class CitingCasesQuerysetViaESTest(TestCase):
    fixtures = [
        "locations/countries.json",
        "locations/states.json",
        "locations/cities.json",
        "courts/courts.json",
        "cases/cases.json",
    ]

    def _call(self, pks, total, **kwargs):
        """Run the helper with ES id resolution stubbed.

        The full-document ``search`` path must not be used: it returns
        stored document bodies (``_source``), which for 10k citing cases
        is enough to trip Elasticsearch's circuit breaker.
        """
        with (
            patch.object(
                MockElasticsearchBackend,
                "search_ids",
                autospec=True,
                return_value=(pks, total),
            ) as search_ids,
            patch.object(
                MockElasticsearchBackend,
                "search",
                side_effect=AssertionError("full-document ES search used"),
            ),
        ):
            result = citing_cases_queryset_via_es("cited_cases", "99", **kwargs)
        return result, search_ids

    def test_resolves_ids_without_fetching_documents(self):
        (qs, total), search_ids = self._call(["3", "2", "1"], 3)

        # Case 2 is pending review and must not be surfaced.
        self.assertEqual(list(qs.values_list("pk", flat=True)), [1, 3])
        self.assertEqual(total, 3)

        _backend, query_string = search_ids.call_args.args
        self.assertIn("cited_cases", query_string)
        self.assertEqual(search_ids.call_args.kwargs["model_ct"], "cases.case")
        self.assertEqual(search_ids.call_args.kwargs["max_results"], 10000)
        self.assertEqual(search_ids.call_args.kwargs["sort_by"], ["-date"])

    def test_passes_order_and_cap_through(self):
        (qs, _total), search_ids = self._call(
            ["1", "3"], 2, max_results=50, order_by="date"
        )

        self.assertEqual(list(qs.values_list("pk", flat=True)), [3, 1])
        self.assertEqual(search_ids.call_args.kwargs["max_results"], 50)
        self.assertEqual(search_ids.call_args.kwargs["sort_by"], ["date"])

    def test_no_hits_returns_empty_queryset(self):
        (qs, total), _search_ids = self._call([], 0)

        self.assertFalse(qs.exists())
        self.assertEqual(total, 0)
