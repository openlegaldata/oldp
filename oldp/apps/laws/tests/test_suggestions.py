"""Tests for law-book code ``did_you_mean`` suggestions."""

from django.test import SimpleTestCase, TestCase

from oldp.apps.laws.suggestions import closest_codes, suggest_book_codes

CODES = ["BGB", "StGB", "StPO", "DSGVO", "GG", "HGB", "ZPO", "BGBEG"]


class ClosestCodesTest(SimpleTestCase):
    """Pure matching logic — no DB."""

    def test_empty_query_returns_nothing(self):
        self.assertEqual(closest_codes("", CODES), [])
        self.assertEqual(closest_codes(None, CODES), [])

    def test_trailing_typo_via_prefix(self):
        # "DSGVOO" -> "DSGVO" (existing code is a prefix of the query)
        self.assertIn("DSGVO", closest_codes("DSGVOO", CODES))

    def test_query_is_prefix_of_existing(self):
        # "BGBE" -> "BGBEG" (query is a prefix of an existing code)
        self.assertIn("BGBEG", closest_codes("BGBE", CODES))

    def test_case_insensitive(self):
        # Lower-case typo still resolves to the canonical upper-case code.
        self.assertIn("BGB", closest_codes("bgbb ", CODES))

    def test_single_char_typo_via_edit_distance(self):
        # "StPOO" should surface StPO
        self.assertIn("StPO", closest_codes("StPOO", CODES))

    def test_exact_match_excluded(self):
        # An exact (case-insensitive) hit is not a "suggestion".
        self.assertNotIn("BGB", closest_codes("BGB", CODES))

    def test_single_char_query_is_ignored(self):
        # Degenerate 1-char query would prefix-match everything → bail.
        self.assertEqual(closest_codes("B", CODES), [])

    def test_prefix_match_ranked_before_fuzzy(self):
        # "DSGVOO" -> DSGVO is a prefix hit and must come first, ahead of any
        # edit-distance noise.
        self.assertEqual(closest_codes("DSGVOO", CODES)[0], "DSGVO")

    def test_respects_limit(self):
        self.assertLessEqual(len(closest_codes("BG", CODES, limit=2)), 2)

    def test_dedupes_case_revision_variants(self):
        # Multiple casings/revisions of the same code collapse to one.
        out = closest_codes("dsgvoo", ["DSGVO", "dsgvo", "DSGVO"])
        self.assertEqual(out.count("DSGVO"), 1)


class SuggestBookCodesDbTest(TestCase):
    """DB-backed path: only accepted books are considered."""

    def _make_book(self, code, review_status="accepted"):
        from oldp.apps.laws.models import LawBook

        return LawBook.objects.create(
            code=code,
            title=f"{code} title",
            slug=code.lower(),
            review_status=review_status,
            latest=True,
        )

    def test_suggests_existing_accepted_codes(self):
        self._make_book("BGB")
        self._make_book("StGB")
        self.assertIn("BGB", suggest_book_codes("BGBB"))

    def test_ignores_non_accepted_books(self):
        self._make_book("BGB", review_status="pending")
        self.assertEqual(suggest_book_codes("BGBB"), [])
