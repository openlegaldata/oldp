"""Tests for the law full-name → code synonym generation (#15)."""

import io
import tempfile

from django.core.management import call_command
from django.test import SimpleTestCase, TestCase

from oldp.apps.laws.law_names import build_law_name_map, law_synonym_rules
from oldp.apps.laws.models import LawBook
from oldp.apps.search.analysis import build_german_index_settings, load_law_synonyms


class LawNameMapTestCase(TestCase):
    """``build_law_name_map`` derives a principled name→code map from the
    latest accepted ``LawBook`` rows.
    """

    @staticmethod
    def _book(title, code, slug, latest=True, review_status="accepted"):
        return LawBook.objects.create(
            title=title,
            code=code,
            slug=slug,
            latest=latest,
            review_status=review_status,
        )

    def test_law_name_shaped_titles_map_to_code(self):
        self._book("Kündigungsschutzgesetz", "KSchG", "kschg")
        self._book("Betriebsverfassungsgesetz", "BetrVG", "betrvg")
        self._book("Bürgerliches Gesetzbuch", "BGB", "bgb")
        m = build_law_name_map()
        self.assertEqual(m.get("kündigungsschutzgesetz"), "KSchG")
        self.assertEqual(m.get("betriebsverfassungsgesetz"), "BetrVG")
        # Multi-word canonical name (ends in -gesetzbuch) is included.
        self.assertEqual(m.get("bürgerliches gesetzbuch"), "BGB")

    def test_descriptive_titles_excluded(self):
        # Starts with "Gesetz", does not END in a law suffix → not a code name;
        # also exceeds the word cap.
        self._book("Gesetz über die Angelegenheiten der Vertriebenen", "BVFG", "bvfg")
        m = build_law_name_map()
        self.assertNotIn("gesetz über die angelegenheiten der vertriebenen", m)

    def test_version_suffix_stripped_from_code(self):
        self._book("Bundesdatenschutzgesetz", "BDSG 1990", "bdsg-1990")
        m = build_law_name_map()
        self.assertEqual(m.get("bundesdatenschutzgesetz"), "BDSG")

    def test_one_char_and_self_codes_skipped(self):
        self._book("Xgesetz", "X", "xgesetz")  # 1-char code → too ambiguous
        self._book("Sondergesetz", "Sondergesetz", "sondergesetz")  # title == code
        m = build_law_name_map()
        self.assertNotIn("xgesetz", m)
        self.assertNotIn("sondergesetz", m)

    def test_only_latest_accepted_books(self):
        self._book("Altgesetz", "AltG", "altg", latest=False)
        self._book("Pendinggesetz", "PendG", "pendg", review_status="pending")
        m = build_law_name_map()
        self.assertNotIn("altgesetz", m)
        self.assertNotIn("pendinggesetz", m)

    def test_command_writes_rules(self):
        self._book("Kündigungsschutzgesetz", "KSchG", "kschg")
        with tempfile.NamedTemporaryFile(
            "r", suffix=".txt", delete=False, encoding="utf-8"
        ) as fh:
            path = fh.name
        call_command("generate_law_synonyms", output=path, stdout=io.StringIO())
        with open(path, encoding="utf-8") as fh:
            content = fh.read()
        self.assertIn(
            "kündigungsschutzgesetz => kündigungsschutzgesetz, kschg", content
        )


class LawSynonymRulesTestCase(SimpleTestCase):
    """``law_synonym_rules`` renders directional ``name => name, code`` rules,
    and the analyzer build accepts them as a query-time ``synonym_graph``.
    """

    def test_rule_format_is_directional_and_lowercased(self):
        rules = law_synonym_rules(
            {"kündigungsschutzgesetz": "KSchG", "sozialgesetzbuch": "SGB V"}
        )
        self.assertIn("kündigungsschutzgesetz => kündigungsschutzgesetz, kschg", rules)
        # Multi-token code stays intact on the RHS (synonym_graph handles it).
        self.assertIn("sozialgesetzbuch => sozialgesetzbuch, sgb v", rules)

    def test_load_law_synonyms_skips_comments_and_blanks(self):
        with tempfile.NamedTemporaryFile(
            "w", suffix=".txt", delete=False, encoding="utf-8"
        ) as fh:
            fh.write("# header\n\nkschg-name => kschg-name, kschg\n")
            path = fh.name
        self.assertEqual(load_law_synonyms(path), ["kschg-name => kschg-name, kschg"])

    def test_law_synonyms_join_query_time_graph(self):
        # Passed in the concept (query-time synonym_graph) bucket; must appear
        # in the search analyzer chain only, never in the index chain.
        rules = ["kündigungsschutzgesetz => kündigungsschutzgesetz, kschg"]
        settings = build_german_index_settings([], rules)
        analysis = settings["settings"]["analysis"]
        self.assertEqual(
            analysis["filter"]["concept_synonyms"]["type"], "synonym_graph"
        )
        self.assertIn(rules[0], analysis["filter"]["concept_synonyms"]["synonyms"])
        self.assertIn(
            "concept_synonyms", analysis["analyzer"]["german_legal_search"]["filter"]
        )
        self.assertNotIn(
            "concept_synonyms", analysis["analyzer"]["german_legal"]["filter"]
        )
