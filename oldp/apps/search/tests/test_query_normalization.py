"""Unit tests for typographic-quote query normalization.

Covers ``normalize_search_query`` (the pure helper) and proves the
downstream effect: after normalization a phrase pasted with German
typographic quotes („…") or guillemets (»…«) is parsed by Haystack's
``AutoQuery`` as an exact-phrase query (ASCII ``"…"``), instead of
degrading to loose AND terms.
"""

from django.test import SimpleTestCase
from haystack import connections
from haystack.inputs import AutoQuery

from oldp.apps.search.utils import normalize_search_query


class NormalizeSearchQueryTest(SimpleTestCase):
    def test_empty_and_none(self):
        self.assertEqual(normalize_search_query(""), "")
        self.assertEqual(normalize_search_query(None), "")

    def test_german_low_high_quotes_become_ascii(self):
        self.assertEqual(
            normalize_search_query("„Treu und Glauben“"),
            '"Treu und Glauben"',
        )

    def test_curly_quotes_become_ascii(self):
        self.assertEqual(
            normalize_search_query("“Eigenbedarf”"),
            '"Eigenbedarf"',
        )

    def test_guillemets_both_directions_become_ascii(self):
        # German nests guillemets reversed (»…«); orientation is irrelevant
        # because AutoQuery only pairs ASCII double quotes.
        self.assertEqual(
            normalize_search_query("»Treu und Glauben«"),
            '"Treu und Glauben"',
        )
        self.assertEqual(
            normalize_search_query("«Treu und Glauben»"),
            '"Treu und Glauben"',
        )

    def test_prime_and_fullwidth_become_ascii(self):
        self.assertEqual(normalize_search_query("″x″"), '"x"')
        self.assertEqual(normalize_search_query("＂x＂"), '"x"')

    def test_ascii_quotes_unchanged(self):
        self.assertEqual(
            normalize_search_query('"Treu und Glauben"'),
            '"Treu und Glauben"',
        )

    def test_plain_text_unchanged(self):
        self.assertEqual(
            normalize_search_query("Eigenbedarf Kündigung"),
            "Eigenbedarf Kündigung",
        )

    def test_unbalanced_quote_is_still_mapped(self):
        # The most likely real-world paste error: an opening typographic
        # quote without a close. It must still map to ASCII; AutoQuery
        # harmlessly drops the dangling delimiter downstream.
        self.assertEqual(
            normalize_search_query("„Treu und Glauben"),
            '"Treu und Glauben',
        )

    def test_mixed_quote_styles_in_one_query(self):
        self.assertEqual(
            normalize_search_query("„foo“ und »bar«"),
            '"foo" und "bar"',
        )


class AutoQueryPhraseEffectTest(SimpleTestCase):
    """Regression guard for the actual user-visible behaviour: the
    normalized string must be parsed by AutoQuery as a single ASCII
    phrase, while the raw typographic form is not.
    """

    def _prepared(self, raw):
        query = connections["default"].get_query()
        return AutoQuery(raw).prepare(query)

    def test_smart_quotes_without_normalization_are_not_a_phrase(self):
        prepared = self._prepared("„Treu und Glauben“")
        self.assertNotIn('"Treu und Glauben"', prepared)

    def test_smart_quotes_after_normalization_form_a_phrase(self):
        prepared = self._prepared(normalize_search_query("„Treu und Glauben“"))
        self.assertEqual(prepared, '"Treu und Glauben"')

    def test_guillemets_after_normalization_form_a_phrase(self):
        prepared = self._prepared(normalize_search_query("»Treu und Glauben«"))
        self.assertEqual(prepared, '"Treu und Glauben"')
