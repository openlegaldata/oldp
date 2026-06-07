"""Unit tests for the custom SearchBackend kwargs construction."""

from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase, override_settings

from oldp.apps.search.search_backend import SearchBackend


def _make_backend():
    """Instantiate SearchBackend without connecting to ES."""
    with patch.object(SearchBackend, "__init__", return_value=None):
        b = SearchBackend.__new__(SearchBackend)
        SearchBackend.__init__(b)
    b.connection_alias = "default"
    b.RESERVED_WORDS = ()
    b.include_spelling = False
    return b


class HighlightKwargsTest(SimpleTestCase):
    """Highlight kwargs must include max_analyzed_offset to avoid 400s on
    long doc fields (see incident 2026-05-05: case texts >1MB triggered
    search_phase_execution_exception in ES highlighter).
    """

    def setUp(self):
        index = MagicMock()
        index.document_field = "text"
        connection = MagicMock()
        connection.get_unified_index.return_value = index
        patcher = patch(
            "oldp.apps.search.search_backend.haystack.connections",
            {"default": connection},
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_highlight_true_sets_max_analyzed_offset(self):
        backend = _make_backend()
        kwargs = backend.build_search_kwargs("test", highlight=True)
        self.assertIn("highlight", kwargs)
        self.assertEqual(kwargs["highlight"]["max_analyzed_offset"], 1_000_000)

    def test_highlight_false_omits_highlight_kwarg(self):
        backend = _make_backend()
        kwargs = backend.build_search_kwargs("test", highlight=False)
        self.assertNotIn("highlight", kwargs)

    def test_caller_overrides_can_replace_max_analyzed_offset(self):
        backend = _make_backend()
        kwargs = backend.build_search_kwargs(
            "test", highlight={"max_analyzed_offset": 500_000}
        )
        self.assertEqual(kwargs["highlight"]["max_analyzed_offset"], 500_000)

    def test_caller_overrides_preserve_max_analyzed_offset_when_not_set(self):
        backend = _make_backend()
        kwargs = backend.build_search_kwargs(
            "test", highlight={"fields": {"text": {"fragment_size": 200}}}
        )
        self.assertEqual(kwargs["highlight"]["max_analyzed_offset"], 1_000_000)


class IsLatestFilterTest(SimpleTestCase):
    """The build_search_kwargs body must always add a filter that
    excludes ``django_ct=laws.law AND is_latest=False`` so stale law
    revisions don't reach the haystack hydration loop (see incident
    2026-05-27: BGB stale-revision docs caused 247 ES round-trips per
    /search/?q=BGB request).
    """

    def setUp(self):
        index = MagicMock()
        index.document_field = "text"
        connection = MagicMock()
        connection.get_unified_index.return_value = index
        patcher = patch(
            "oldp.apps.search.search_backend.haystack.connections",
            {"default": connection},
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    @staticmethod
    def _extract_filters(kwargs):
        """Pull the list of filter clauses out of a bool-wrapped query."""
        query = kwargs.get("query", {})
        if "bool" not in query or "filter" not in query["bool"]:
            return []
        f = query["bool"]["filter"]
        # A single filter is set directly; multiple get wrapped as bool/must
        if isinstance(f, dict) and "bool" in f and "must" in f["bool"]:
            return f["bool"]["must"]
        return [f]

    def test_is_latest_filter_always_present(self):
        backend = _make_backend()
        kwargs = backend.build_search_kwargs("test", highlight=False)
        filters = self._extract_filters(kwargs)
        found = any(
            isinstance(f, dict)
            and "bool" in f
            and "must_not" in f["bool"]
            and isinstance(f["bool"]["must_not"], dict)
            and "bool" in f["bool"]["must_not"]
            and any(
                {"term": {"is_latest": False}} == clause
                for clause in f["bool"]["must_not"]["bool"].get("must", [])
            )
            for f in filters
        )
        self.assertTrue(
            found,
            f"expected is_latest=False exclusion in query filters; got {filters!r}",
        )

    def test_is_latest_filter_present_with_narrow_queries(self):
        backend = _make_backend()
        kwargs = backend.build_search_kwargs(
            "test", highlight=False, narrow_queries={"facet_model_name:Case"}
        )
        filters = self._extract_filters(kwargs)
        # both the narrow_query and the is_latest exclusion must be there
        self.assertGreaterEqual(len(filters), 2)


class GermanAnalyzerSchemaTest(SimpleTestCase):
    """``build_schema`` must apply the ``german_legal`` analyzer to the
    free-text fields (text/title/exact_matches) and leave the citation /
    structural / facet fields on their defaults, so German morphology
    works in search without breaking the citation filter or facets.
    """

    @staticmethod
    def _real_fields():
        # Build a UnifiedIndex from the actual SearchIndex classes so the
        # assertion reflects the real field set, not a hand-rolled mock.
        from haystack.utils.loading import UnifiedIndex

        from oldp.apps.cases.search_indexes import CaseIndex
        from oldp.apps.laws.search_indexes import LawIndex

        ui = UnifiedIndex()
        ui.build(indexes=[CaseIndex(), LawIndex()])
        return ui.fields

    def test_german_analyzer_on_text_fields(self):
        backend = _make_backend()
        _, mapping = backend.build_schema(self._real_fields())
        for field_name in ("text", "title", "exact_matches"):
            self.assertEqual(
                mapping[field_name].get("analyzer"),
                "german_legal",
                f"{field_name} should use the german_legal index analyzer",
            )
            self.assertEqual(
                mapping[field_name].get("search_analyzer"),
                "german_legal_search",
                f"{field_name} should use the german_legal_search analyzer",
            )

    def test_citation_and_structural_fields_not_germanized(self):
        backend = _make_backend()
        _, mapping = backend.build_schema(self._real_fields())
        # Citation tokens must NOT be German-stemmed (would break the filter).
        for field_name in ("cited_laws", "cited_cases", "slug"):
            self.assertNotEqual(
                mapping[field_name].get("analyzer"),
                "german_legal",
                f"{field_name} must not use the german_legal analyzer",
            )
        # Facet fields stay keyword (no analyzer at all).
        self.assertEqual(mapping["court_exact"]["type"], "keyword")
        self.assertNotIn("analyzer", mapping["court_exact"])


class ElasticsearchTimeoutTest(SimpleTestCase):
    """``SearchBackend`` reads ``settings.ELASTICSEARCH_TIMEOUT`` so
    ops can tune the ES per-call timeout without editing
    ``HAYSTACK_CONNECTIONS``. The tuned value must propagate into
    the elasticsearch-py client constructor (where it ends up as the
    socket timeout for every query).
    """

    def test_index_settings_deep_merge_keeps_haystack_and_german(self):
        """Merging ELASTICSEARCH_INDEX_SETTINGS must ADD the german_legal
        analyzer without dropping haystack's built-in ngram analyzers —
        a shallow merge of the ``analysis`` key would break autocomplete.
        """
        with patch(
            "haystack.backends.elasticsearch7_backend.elasticsearch.Elasticsearch"
        ):
            backend = SearchBackend(
                "default",
                URL="http://localhost:9200/",
                INDEX_NAME="oldp_test",
            )
        analyzers = backend.DEFAULT_SETTINGS["settings"]["analysis"]["analyzer"]
        self.assertIn("german_legal", analyzers)
        self.assertIn("german_legal_search", analyzers)
        self.assertIn("ngram_analyzer", analyzers)
        self.assertIn("edgengram_analyzer", analyzers)
        filters = backend.DEFAULT_SETTINGS["settings"]["analysis"]["filter"]
        self.assertIn("german_light_stem", filters)
        self.assertIn("legal_synonyms", filters)
        self.assertIn("concept_synonyms", filters)
        self.assertIn("haystack_edgengram", filters)
        # concept_synonyms must be query-time only: present in the search
        # analyzer chain, absent from the index analyzer chain.
        self.assertIn("concept_synonyms", analyzers["german_legal_search"]["filter"])
        self.assertNotIn("concept_synonyms", analyzers["german_legal"]["filter"])

    def test_legal_synonyms_filter_wired_in_order(self):
        """The german_legal analyzer must run legal_synonyms after lowercase
        but before normalization/stemming, so a synonym and its target
        collapse to the same lemma.
        """
        with patch(
            "haystack.backends.elasticsearch7_backend.elasticsearch.Elasticsearch"
        ):
            backend = SearchBackend(
                "default", URL="http://localhost:9200/", INDEX_NAME="oldp_test"
            )
        analysis = backend.DEFAULT_SETTINGS["settings"]["analysis"]
        self.assertIn("legal_synonyms", analysis["filter"])
        chain = analysis["analyzer"]["german_legal"]["filter"]
        self.assertEqual(
            chain,
            [
                "lowercase",
                "legal_synonyms",
                "german_normalization",
                "german_light_stem",
            ],
        )

    def test_legal_synonyms_list_is_well_formed(self):
        from oldp.settings import LEGAL_SYNONYMS

        seen_terms = set()
        for line in LEGAL_SYNONYMS:
            terms = [t.strip() for t in line.split(",")]
            self.assertGreaterEqual(len(terms), 2, f"need >=2 terms: {line!r}")
            for t in terms:
                self.assertTrue(t, f"empty term in {line!r}")
                self.assertEqual(t, t.lower(), f"synonym must be lower-case: {t!r}")
                # A term appearing in two groups would merge unrelated sets.
                self.assertNotIn(t, seen_terms, f"duplicate synonym term: {t!r}")
                seen_terms.add(t)

    def test_concept_synonyms_are_directional_and_lowercase(self):
        from oldp.settings import CONCEPT_SYNONYMS

        for line in CONCEPT_SYNONYMS:
            self.assertIn("=>", line, f"concept synonym must be directional: {line!r}")
            lhs, rhs = line.split("=>")
            self.assertTrue(lhs.strip() and rhs.strip(), f"empty side: {line!r}")
            self.assertEqual(line, line.lower(), f"must be lower-case: {line!r}")
            # Directional mapping should echo its LHS terms in the RHS so the
            # original colloquial term still matches its own documents.
            rhs_terms = {t.strip() for t in rhs.split(",")}
            for lhs_term in (t.strip() for t in lhs.split(",")):
                self.assertIn(
                    lhs_term,
                    rhs_terms,
                    f"LHS {lhs_term!r} should be echoed in RHS of {line!r}",
                )

    @override_settings(ELASTICSEARCH_TIMEOUT=7)
    def test_settings_timeout_overrides_connection_option(self):
        with patch(
            "haystack.backends.elasticsearch7_backend.elasticsearch.Elasticsearch"
        ) as fake_es:
            SearchBackend(
                "default",
                URL="http://localhost:9200/",
                INDEX_NAME="oldp_test",
                TIMEOUT=99,  # should be ignored in favour of settings value
            )
        # elasticsearch-py was constructed with timeout=7
        self.assertEqual(fake_es.call_args.kwargs.get("timeout"), 7)

    @override_settings(ELASTICSEARCH_TIMEOUT=3)
    def test_settings_timeout_takes_precedence_over_kwarg(self):
        """Even if a caller passes an explicit TIMEOUT in connection
        options (e.g. legacy ``HAYSTACK_CONNECTIONS`` config), the
        settings value wins — keeps a single knob for ops to tune.
        """
        with patch(
            "haystack.backends.elasticsearch7_backend.elasticsearch.Elasticsearch"
        ) as fake_es:
            SearchBackend(
                "default",
                URL="http://localhost:9200/",
                INDEX_NAME="oldp_test",
                TIMEOUT=99,
            )
        self.assertEqual(fake_es.call_args.kwargs.get("timeout"), 3)
