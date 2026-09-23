"""Citation ranges must not expand without bound.

``_expand_range`` turned a citation with a numeric ``range_end`` into one
``Reference`` per integer with no ceiling. Production law table-of-contents
pages carried misparsed markers -- ``§§ 154 bis 16617``, ``§§ 1 bis 3127`` --
where a section number sits beside an unrelated number and the two are joined
into a range. VwGO has roughly 200 sections, so 16,464 rows were written for
one marker and nearly all pointed at sections that do not exist.

The rendering side then emitted one hidden div per reference, producing 7.4 MB
of HTML and an 88-second render that nginx cut off at 10s as a 504.
"""

from django.test import TestCase
from refex.citations import LawCitation
from refex.document import Span

from oldp.apps.references.processing.processing_steps.extract_refs import (
    BaseExtractRefs,
)


class ExpandRangeCapTestCase(TestCase):
    @staticmethod
    def _cite(number, range_end):
        return LawCitation(
            span=Span(0, 9, "§§ x bis y"),
            book="VwGO",
            number=str(number),
            unit="paragraph",
            range_end=str(range_end) if range_end is not None else None,
        )

    def test_legitimate_wide_block_citation_still_expands(self):
        """Real block cites get wide: §§ 253 bis 591 ZPO is 339 sections."""
        out = BaseExtractRefs._expand_range(self._cite(253, 591))
        self.assertEqual(len(out), 339)

    def test_small_range_still_expands(self):
        """The legacy convention must survive: 12-14 -> three citations."""
        out = BaseExtractRefs._expand_range(self._cite(12, 14))
        self.assertEqual([c.number for c in out], ["12", "13", "14"])

    def test_range_at_the_limit_expands(self):
        limit = BaseExtractRefs.RANGE_EXPANSION_LIMIT
        out = BaseExtractRefs._expand_range(self._cite(1, limit))
        self.assertEqual(len(out), limit)

    def test_range_past_the_limit_is_not_expanded(self):
        limit = BaseExtractRefs.RANGE_EXPANSION_LIMIT
        out = BaseExtractRefs._expand_range(self._cite(1, limit + 1))
        self.assertEqual(len(out), 1)
        self.assertIsNone(out[0].range_end)
        self.assertEqual(out[0].number, "1")

    def test_production_misparse_yields_one_reference(self):
        """The actual marker that took the page down: 154-16617."""
        out = BaseExtractRefs._expand_range(self._cite(154, 16617))
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0].number, "154")

    def test_oversized_range_is_logged(self):
        """The warning is the feed for finding the parser bugs behind these."""
        with self.assertLogs(
            "oldp.apps.references.processing.processing_steps.extract_refs",
            level="WARNING",
        ) as logs:
            BaseExtractRefs._expand_range(self._cite(154, 16617))
        self.assertTrue(any("16617" in line for line in logs.output))

    def test_non_range_citation_untouched(self):
        out = BaseExtractRefs._expand_range(self._cite(823, None))
        self.assertEqual(len(out), 1)

    def test_non_integer_bounds_untouched(self):
        cite = LawCitation(
            span=Span(0, 9, "§§ 12a-14b"),
            book="BGB",
            number="12a",
            unit="paragraph",
            range_end="14b",
        )
        out = BaseExtractRefs._expand_range(cite)
        self.assertEqual(out, [cite])

    def test_inverted_range_untouched(self):
        out = BaseExtractRefs._expand_range(self._cite(14, 12))
        self.assertEqual(len(out), 1)
