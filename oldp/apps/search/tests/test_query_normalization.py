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

from oldp.apps.search.utils import (
    normalize_search_query,
    prepare_search_query,
    strip_query_stopwords,
)


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


class StripQueryStopwordsTest(SimpleTestCase):
    def test_removes_function_words_keeps_content(self):
        self.assertEqual(
            strip_query_stopwords(
                "Welche Frist habe ich für den Einspruch gegen den Bußgeldbescheid"
            ),
            "Frist Einspruch Bußgeldbescheid",
        )

    def test_keeps_phrase_contents_verbatim(self):
        # "und" inside a quoted phrase must survive; bare "der" is dropped.
        self.assertEqual(
            strip_query_stopwords('der "Treu und Glauben" Grundsatz'),
            '"Treu und Glauben" Grundsatz',
        )

    def test_preserves_exclude_and_required_operators(self):
        self.assertEqual(
            strip_query_stopwords("die Kündigung -strafrecht +mietrecht"),
            "Kündigung -strafrecht +mietrecht",
        )

    def test_preserves_boolean_and_field_scoped(self):
        self.assertEqual(
            strip_query_stopwords("urteil OR beschluss"), "urteil OR beschluss"
        )
        self.assertEqual(
            strip_query_stopwords("die title:Mietrecht"), "title:Mietrecht"
        )

    def test_all_stopword_query_is_left_intact(self):
        # Nothing discriminative left → run the literal query, don't match all.
        self.assertEqual(strip_query_stopwords("wie ist das"), "wie ist das")

    def test_plain_keyword_query_unchanged(self):
        self.assertEqual(
            strip_query_stopwords("Eigenbedarf Kündigung"), "Eigenbedarf Kündigung"
        )

    def test_strips_stopword_with_trailing_punctuation(self):
        # "den," (comma) and "ich?" should still be recognised as stopwords.
        self.assertEqual(
            strip_query_stopwords("Einspruch gegen den, Bußgeldbescheid"),
            "Einspruch Bußgeldbescheid",
        )

    def test_unbalanced_quote_not_auto_closed_into_phrase(self):
        # A stray opening quote must NOT turn the rest into an exact phrase;
        # the bare stopword is still dropped and the quote left in place.
        self.assertEqual(
            strip_query_stopwords('die Kündigung "Treu Glauben'),
            'Kündigung "Treu Glauben',
        )

    def test_empty(self):
        self.assertEqual(strip_query_stopwords(""), "")
        self.assertEqual(strip_query_stopwords(None), "")


class PrepareSearchQueryTest(SimpleTestCase):
    def test_combines_quote_normalization_and_stopword_strip(self):
        # „…" phrase preserved (and normalized to ASCII), bare "der" dropped.
        self.assertEqual(
            prepare_search_query('der „Treu und Glauben" Grundsatz'),
            '"Treu und Glauben" Grundsatz',
        )

    def test_natural_language_question(self):
        self.assertEqual(
            prepare_search_query("Wie hoch ist die Abfindung bei Kündigung"),
            "hoch Abfindung Kündigung",
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
