"""Tests for externally-loaded search synonyms + analyzer construction.

Covers the pure ``load_search_synonyms`` / ``build_german_index_settings``
helpers (the synonym vocabulary itself is deployment data and lives outside
the generic oldp app). When ``OLDP_SEARCH_SYNONYMS_FILE`` is configured
(e.g. the local dev env points at the OLDP-DE file), the well-formedness
test also validates that real file; otherwise it is skipped.
"""

import os
import tempfile

from django.test import SimpleTestCase

from oldp.apps.search.analysis import (
    build_german_index_settings,
    load_search_synonyms,
)

_SAMPLE = """\
# comment
[legal_synonyms]
vermieter, vermieterin
mieter, mieterin

[concept_synonyms]
# a directional rule
blitzer => blitzer, geschwindigkeitsmessung
hartz iv, alg ii => hartz iv, alg ii, arbeitslosengeld ii
"""


class LoadSynonymsTest(SimpleTestCase):
    def test_missing_path_returns_empty(self):
        self.assertEqual(load_search_synonyms(""), ([], []))
        self.assertEqual(load_search_synonyms("/no/such/file"), ([], []))

    def test_parses_sections_and_skips_comments(self):
        with tempfile.NamedTemporaryFile(
            "w", suffix=".txt", delete=False, encoding="utf-8"
        ) as fh:
            fh.write(_SAMPLE)
            path = fh.name
        try:
            legal, concept = load_search_synonyms(path)
        finally:
            os.unlink(path)
        self.assertEqual(legal, ["vermieter, vermieterin", "mieter, mieterin"])
        self.assertEqual(
            concept,
            [
                "blitzer => blitzer, geschwindigkeitsmessung",
                "hartz iv, alg ii => hartz iv, alg ii, arbeitslosengeld ii",
            ],
        )


class BuildGermanIndexSettingsTest(SimpleTestCase):
    def _analysis(self, legal, concept):
        return build_german_index_settings(legal, concept)["settings"]["analysis"]

    def test_no_synonyms_omits_filters(self):
        a = self._analysis([], [])
        self.assertNotIn("legal_synonyms", a["filter"])
        self.assertNotIn("concept_synonyms", a["filter"])
        self.assertEqual(
            a["analyzer"]["german_legal"]["filter"],
            ["lowercase", "german_normalization", "german_light_stem"],
        )

    def test_legal_synonyms_index_and_query(self):
        a = self._analysis(["a, b"], [])
        self.assertEqual(a["filter"]["legal_synonyms"]["type"], "synonym")
        self.assertIn("legal_synonyms", a["analyzer"]["german_legal"]["filter"])
        self.assertIn("legal_synonyms", a["analyzer"]["german_legal_search"]["filter"])

    def test_concept_synonyms_query_only_and_graph(self):
        a = self._analysis([], ["x => x, y"])
        self.assertEqual(a["filter"]["concept_synonyms"]["type"], "synonym_graph")
        # query-time only: in the search chain, NOT the index chain.
        self.assertIn(
            "concept_synonyms", a["analyzer"]["german_legal_search"]["filter"]
        )
        self.assertNotIn("concept_synonyms", a["analyzer"]["german_legal"]["filter"])

    def test_filter_order(self):
        a = self._analysis(["a, b"], ["x => x, y"])
        self.assertEqual(
            a["analyzer"]["german_legal_search"]["filter"],
            [
                "lowercase",
                "legal_synonyms",
                "concept_synonyms",
                "german_normalization",
                "german_light_stem",
            ],
        )


class ConfiguredSynonymsFileTest(SimpleTestCase):
    """Validate the real deployment file when one is configured (else skip)."""

    def setUp(self):
        path = os.environ.get("OLDP_SEARCH_SYNONYMS_FILE", "")
        if not path or not os.path.exists(path):
            self.skipTest("OLDP_SEARCH_SYNONYMS_FILE not configured")
        self.legal, self.concept = load_search_synonyms(path)

    def test_legal_synonyms_well_formed(self):
        seen = set()
        for line in self.legal:
            terms = [t.strip() for t in line.split(",")]
            self.assertGreaterEqual(len(terms), 2, line)
            for t in terms:
                self.assertTrue(t and t == t.lower(), f"bad term {t!r} in {line!r}")
                self.assertNotIn(t, seen, f"duplicate legal term {t!r}")
                seen.add(t)

    def test_concept_synonyms_directional_lowercase(self):
        for line in self.concept:
            self.assertIn("=>", line, f"concept rule must be directional: {line!r}")
            self.assertEqual(line, line.lower(), f"must be lower-case: {line!r}")
            lhs, rhs = line.split("=>")
            rhs_terms = {t.strip() for t in rhs.split(",")}
            for lhs_term in (t.strip() for t in lhs.split(",")):
                self.assertIn(
                    lhs_term, rhs_terms, f"LHS {lhs_term!r} not echoed: {line!r}"
                )
