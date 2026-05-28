"""Test helpers for the ES-backed citing_cases endpoints.

The production helper ``oldp.apps.search.utils.citing_cases_queryset_via_es``
queries Elasticsearch via ``CaseIndex.cited_laws`` / ``CaseIndex.cited_cases``.
Unit tests run with ``MOCK_ES_TESTS=True`` (mock haystack backend) which
returns no hits — so any test that asserts "citing-cases endpoint
returns these specific fixture rows" needs to bypass ES.

This module provides a SQL-backed shim that mirrors the production
helper's signature + return shape, computed from the same
``Reference`` rows the test fixtures create. Apply it to a TestCase
via ``ESCitingCasesShimMixin`` — it starts the patch in ``setUp`` and
stops it in ``tearDown``, so the mock isn't passed to test methods
(which would change their signatures and break ``@override_settings``
and other decorators).

The shim keeps the API/MCP behaviour identical from the consumer's
point of view (paginated Case queryset + total count) while leaving
the production import path under test. The matching production code
remains ES-only — there is no SQL fallback in views / MCP tools.
"""

from unittest.mock import patch


def _sql_citing_cases_queryset(field, value, max_results=10000):
    """Test-only SQL fallback that mirrors ``citing_cases_queryset_via_es``.

    Computes the citing-case ids via the existing SQL helpers in
    ``oldp.apps.references.services.citation_graph`` (which are the
    source of truth that fed the ES indexer in the first place), then
    builds the same hydrated ``Case`` queryset shape the production
    helper returns.
    """
    from oldp.apps.cases.models import Case
    from oldp.apps.references.services import (
        citing_case_ids_for_case,
        citing_case_ids_for_slug_pair,
    )

    if field == "cited_laws":
        book, sep, section = value.partition("__")
        if not sep:
            return Case.objects.none(), 0
        ids = citing_case_ids_for_slug_pair(book, section)
    elif field == "cited_cases":
        case = Case.objects.filter(pk=int(value)).first()
        if case is None:
            return Case.objects.none(), 0
        ids = citing_case_ids_for_case(case)
    else:
        return Case.objects.none(), 0

    ids = list(ids)[:max_results]
    if not ids:
        return Case.objects.none(), 0
    qs = (
        Case.objects.filter(id__in=ids, review_status="accepted")
        .select_related("court")
        .defer(*Case.defer_fields_list_view)
        .order_by("-date")
    )
    return qs, qs.count()


class ESCitingCasesShimMixin:
    """Mixin: monkey-patches ``citing_cases_queryset_via_es`` to the
    SQL fallback for every test in the class.

    Apply to a TestCase via ``class MyTest(ESCitingCasesShimMixin,
    TestCase): ...``. The patch is started in ``setUpClass`` and
    stopped in ``tearDownClass``, so it doesn't interact with the
    test class's per-test ``setUp`` (which existing classes don't
    chain via ``super().setUp()``). Test method signatures stay
    unchanged.

    Tests that exercise the ES failure path should NOT use this
    mixin; ``@patch`` the helper directly with a side-effect-raising
    lambda inside the test.
    """

    @classmethod
    def setUpClass(cls):
        cls._citing_cases_patcher = patch(
            "oldp.apps.search.utils.citing_cases_queryset_via_es",
            side_effect=_sql_citing_cases_queryset,
        )
        cls._citing_cases_patcher.start()
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        cls._citing_cases_patcher.stop()
