"""Tests for court did_you_mean suggestions + get_court integration."""

from django.test import TestCase

from oldp.apps.courts.mcp import CourtTools
from oldp.apps.courts.suggestions import suggest_court_codes, suggest_court_slugs


class CourtSuggestionsTest(TestCase):
    fixtures = [
        "locations/countries.json",
        "locations/states.json",
        "locations/cities.json",
        "courts/courts.json",
    ]

    def test_suggest_court_codes_typo(self):
        # "BVerfGG" / "BGHH" should surface the real codes.
        self.assertIn("BVerfG", suggest_court_codes("BVerfGG"))
        self.assertIn("BGH", suggest_court_codes("BGHH"))

    def test_suggest_court_slugs_typo(self):
        self.assertIn("bverfg", suggest_court_slugs("bverfgg"))

    def test_get_court_unknown_code_returns_suggestions(self):
        result = CourtTools().get_court(code="BVerfGG")
        self.assertIn("error", result)
        self.assertIn("BVerfG", result.get("suggestions", []))

    def test_get_court_unknown_slug_returns_suggestions(self):
        result = CourtTools().get_court(slug="bverfgg")
        self.assertIn("error", result)
        self.assertIn("bverfg", result.get("suggestions", []))

    def test_get_court_found_has_no_suggestions(self):
        result = CourtTools().get_court(code="BGH")
        self.assertNotIn("error", result)
        self.assertNotIn("suggestions", result)
