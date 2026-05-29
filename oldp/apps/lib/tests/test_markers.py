"""Unit tests for the markers module.

Tests cover:
- BaseMarker class and its methods
- insert_markers function with various scenarios
- Marker overlap detection
"""

import logging
from unittest.mock import patch

from django.test import TestCase, tag

from oldp.apps.lib.markers import BaseMarker, insert_markers

logger = logging.getLogger(__name__)


class ConcreteMarker(BaseMarker):
    """Concrete implementation of BaseMarker for testing."""

    def __init__(self, start: int, end: int, marker_id: str = "test"):
        self.start = start
        self.end = end
        self.marker_id = marker_id

    def get_start_position(self) -> int:
        return self.start

    def get_end_position(self) -> int:
        return self.end

    def get_marker_open_format(self) -> str:
        return "[ref={marker_id}]"

    def get_marker_close_format(self) -> str:
        return "[/ref]"


@tag("lib", "markers")
class BaseMarkerTestCase(TestCase):
    """Tests for the BaseMarker abstract class."""

    def test_get_marker_open(self):
        """Test that get_marker_open formats the open tag correctly."""
        marker = ConcreteMarker(0, 5, marker_id="abc123")
        self.assertEqual(marker.get_marker_open(), "[ref=abc123]")

    def test_get_marker_close(self):
        """Test that get_marker_close formats the close tag correctly."""
        marker = ConcreteMarker(0, 5, marker_id="abc123")
        self.assertEqual(marker.get_marker_close(), "[/ref]")

    def test_insert_marker_basic(self):
        """Test inserting a marker into content."""
        content = "Hello World"
        marker = ConcreteMarker(0, 5, marker_id="test")

        result, offset = marker.insert_marker(content, 0)

        self.assertEqual(result, "[ref=test]Hello[/ref] World")
        self.assertEqual(offset, len("[ref=test]") + len("[/ref]"))

    def test_insert_marker_middle_of_content(self):
        """Test inserting a marker in the middle of content."""
        content = "Hello beautiful World"
        marker = ConcreteMarker(6, 15, marker_id="mid")

        result, offset = marker.insert_marker(content, 0)

        self.assertEqual(result, "Hello [ref=mid]beautiful[/ref] World")

    def test_insert_marker_with_offset(self):
        """Test inserting a marker with an existing offset."""
        content = "[ref=first]Hello[/ref] World"
        marker = ConcreteMarker(6, 11, marker_id="second")
        initial_offset = len("[ref=first]") + len("[/ref]")

        # After first marker, "World" starts at position 6 + initial_offset
        result, offset = marker.insert_marker(content, initial_offset)

        # The marker should be inserted accounting for the offset
        self.assertIn("[ref=second]", result)
        self.assertIn("[/ref]", result)

    def test_insert_marker_at_end(self):
        """Test inserting a marker at the end of content."""
        content = "Hello World"
        marker = ConcreteMarker(6, 11, marker_id="end")

        result, offset = marker.insert_marker(content, 0)

        self.assertEqual(result, "Hello [ref=end]World[/ref]")


@tag("lib", "markers")
class InsertMarkersTestCase(TestCase):
    """Tests for the insert_markers function."""

    def test_insert_markers_empty_list(self):
        """Test with no markers."""
        content = "Hello World"
        result = insert_markers(content, [])

        self.assertEqual(result, content)

    def test_insert_markers_single_marker(self):
        """Test with a single marker."""
        content = "Hello World"
        markers = [ConcreteMarker(0, 5, marker_id="1")]

        result = insert_markers(content, markers)

        self.assertEqual(result, "[ref=1]Hello[/ref] World")

    def test_insert_markers_multiple_non_overlapping(self):
        """Test with multiple non-overlapping markers."""
        content = "Hello beautiful World"
        markers = [
            ConcreteMarker(0, 5, marker_id="1"),
            ConcreteMarker(16, 21, marker_id="2"),
        ]

        result = insert_markers(content, markers)

        self.assertEqual(result, "[ref=1]Hello[/ref] beautiful [ref=2]World[/ref]")

    def test_insert_markers_sorted_by_position(self):
        """Test that markers are sorted by position regardless of input order."""
        content = "Hello beautiful World"
        # Markers provided in reverse order
        markers = [
            ConcreteMarker(16, 21, marker_id="2"),
            ConcreteMarker(0, 5, marker_id="1"),
        ]

        result = insert_markers(content, markers)

        # Should be sorted and applied correctly
        self.assertEqual(result, "[ref=1]Hello[/ref] beautiful [ref=2]World[/ref]")

    @patch("oldp.apps.lib.markers.logger")
    def test_insert_markers_overlapping_previous(self, mock_logger):
        """Test that overlapping markers are logged and skipped."""
        content = "Hello World"
        markers = [
            ConcreteMarker(0, 7, marker_id="1"),  # "Hello W"
            ConcreteMarker(5, 11, marker_id="2"),  # " World" - overlaps
        ]

        result = insert_markers(content, markers)

        # Both markers are skipped due to overlap detection
        # First marker overlaps with next, second overlaps with previous
        mock_logger.error.assert_called()
        # Neither marker should be inserted due to overlap
        self.assertNotIn("[ref=1]", result)
        self.assertNotIn("[ref=2]", result)
        self.assertEqual(result, "Hello World")

    @patch("oldp.apps.lib.markers.logger")
    def test_insert_markers_overlapping_next(self, mock_logger):
        """Test that overlapping markers with next are detected."""
        content = "Hello World"
        # These markers overlap
        markers = [
            ConcreteMarker(0, 8, marker_id="1"),  # "Hello Wo"
            ConcreteMarker(6, 11, marker_id="2"),  # "World" - overlaps with previous
        ]

        _ = insert_markers(content, markers)

        # An error should be logged
        mock_logger.error.assert_called()

    def test_insert_markers_adjacent_treated_as_overlapping(self):
        """Test that adjacent markers (end == start) are treated as overlapping."""
        content = "HelloWorld"
        markers = [
            ConcreteMarker(0, 5, marker_id="1"),  # "Hello" ends at 5
            ConcreteMarker(5, 10, marker_id="2"),  # "World" starts at 5
        ]

        result = insert_markers(content, markers)

        # Adjacent markers where end == start are considered overlapping
        # and both are skipped
        self.assertEqual(result, "HelloWorld")

    def test_insert_markers_non_adjacent_sequential(self):
        """Test that non-adjacent sequential markers work correctly."""
        content = "Hello World"
        markers = [
            ConcreteMarker(0, 5, marker_id="1"),  # "Hello" ends at 5
            ConcreteMarker(6, 11, marker_id="2"),  # "World" starts at 6 (gap of 1)
        ]

        result = insert_markers(content, markers)

        self.assertEqual(result, "[ref=1]Hello[/ref] [ref=2]World[/ref]")

    def test_insert_markers_three_markers(self):
        """Test with three non-overlapping markers."""
        content = "One Two Three"
        markers = [
            ConcreteMarker(0, 3, marker_id="a"),
            ConcreteMarker(4, 7, marker_id="b"),
            ConcreteMarker(8, 13, marker_id="c"),
        ]

        result = insert_markers(content, markers)

        self.assertEqual(result, "[ref=a]One[/ref] [ref=b]Two[/ref] [ref=c]Three[/ref]")

    def test_insert_markers_empty_content(self):
        """Test with empty content."""
        content = ""
        markers = []

        result = insert_markers(content, markers)

        self.assertEqual(result, "")

    def test_insert_markers_special_characters(self):
        """Test markers around special characters."""
        content = "Hello & World <test>"
        markers = [ConcreteMarker(6, 7, marker_id="amp")]

        result = insert_markers(content, markers)

        self.assertEqual(result, "Hello [ref=amp]&[/ref] World <test>")


class ExpectedTextMarker(BaseMarker):
    """Marker that carries a plain-text expectation for the (start, end) slice.

    Models :class:`oldp.apps.references.models.ReferenceMarker`: the
    citation text is captured at extraction time and the render-time
    integrity guard compares it against ``content[start:end]``.
    """

    def __init__(self, start: int, end: int, text: str, marker_id: str = "test"):
        self.start = start
        self.end = end
        self.text = text
        self.marker_id = marker_id

    def get_start_position(self) -> int:
        return self.start

    def get_end_position(self) -> int:
        return self.end

    def get_expected_text(self) -> str:
        return self.text

    def get_marker_open_format(self) -> str:
        return "[ref={marker_id}]"

    def get_marker_close_format(self) -> str:
        return "[/ref]"


@tag("lib", "markers")
class IntegrityGuardTestCase(TestCase):
    """Tests for the stale-marker integrity guard in ``insert_markers``."""

    def test_matching_text_is_inserted(self):
        """Marker whose stored slice matches its ``text`` renders normally."""
        content = "Citation: § 25 StVG here"
        markers = [ExpectedTextMarker(10, 19, text="§ 25 StVG", marker_id="ok")]

        result = insert_markers(content, markers)

        self.assertEqual(result, "Citation: [ref=ok]§ 25 StVG[/ref] here")

    @patch("oldp.apps.lib.markers.logger")
    def test_stale_offsets_skip_marker(self, mock_logger):
        """Marker whose slice mismatches ``text`` is skipped, not rendered."""
        # Simulates the prod bug: the stored marker text is "§ 25 StVG"
        # but ``case.content`` was modified so (start, end) now slices
        # an unrelated word fragment.
        content = "Some completely different text here"
        markers = [ExpectedTextMarker(5, 14, text="§ 25 StVG", marker_id="stale")]

        result = insert_markers(content, markers)

        self.assertEqual(result, content)
        mock_logger.warning.assert_called_once()
        # The warning should mention the expected text and what was found.
        args = mock_logger.warning.call_args.args
        self.assertIn("§ 25 StVG", args)

    def test_slice_with_html_entities_matches_plain_text(self):
        """Raw slice with HTML entities normalizes to plain text before compare.

        Reflects how OLDP stores marker offsets: refex's
        ``map_span_to_raw`` returns positions into raw HTML, so
        ``content[start:end]`` can contain ``&#167;`` while ``marker.text``
        holds the decoded ``§``. The guard must accept the match.
        """
        content = "Citation: &#167; 130a Satz 1 VwGO here"
        end = len("Citation: &#167; 130a Satz 1 VwGO")
        markers = [
            ExpectedTextMarker(10, end, text="§ 130a Satz 1 VwGO", marker_id="ent")
        ]

        result = insert_markers(content, markers)

        self.assertIn("[ref=ent]&#167; 130a Satz 1 VwGO[/ref]", result)

    def test_slice_with_inline_tags_matches_after_strip(self):
        """Inline HTML tags inside the slice (RDFa span wrappers etc.)
        are stripped before comparison.
        """
        content = 'See <span class="rdfa">§ 25 StVG</span> for details'
        start = content.index("<span")
        end = content.index("</span>") + len("</span>")
        markers = [ExpectedTextMarker(start, end, text="§ 25 StVG", marker_id="rdfa")]

        result = insert_markers(content, markers)

        self.assertIn('[ref=rdfa]<span class="rdfa">§ 25 StVG</span>[/ref]', result)

    def test_marker_without_expected_text_still_renders(self):
        """``BaseMarker.get_expected_text`` defaults to ``None`` → no check.

        Annotation markers (``CaseMarker``) don't persist a canonical
        text and must keep working unchanged.
        """
        content = "Annotation target here"
        markers = [ConcreteMarker(0, 10, marker_id="ann")]

        result = insert_markers(content, markers)

        self.assertEqual(result, "[ref=ann]Annotation[/ref] target here")


@tag("lib", "markers")
class StaleMarkerReanchorTestCase(TestCase):
    """Fuzzy re-anchor for stale offsets that still appear in content."""

    def test_offset_drift_recovered_by_literal_search(self):
        """A small offset shift on a unique citation is recovered."""
        content = "PREFIX prepended. See § 25 StVG for details."
        # Marker offsets were captured before "PREFIX prepended. " was added
        stored_start = content.index("§ 25 StVG") - len("PREFIX prepended. ")
        stored_end = stored_start + len("§ 25 StVG")
        markers = [
            ExpectedTextMarker(stored_start, stored_end, text="§ 25 StVG", marker_id="r")
        ]

        result = insert_markers(content, markers)

        self.assertIn("[ref=r]§ 25 StVG[/ref]", result)

    def test_entity_encoded_content_recovered(self):
        """Stored slice is in plain text but live content has ``&#167;``.

        Mirrors the prod BGH case where api-time extraction wrote
        marker.text='§ 134 BGB' but stored content keeps the entity
        encoded as ``&#167; 134 BGB`` (length 14 vs 9 → offsets shift
        by 5/case occurrence).
        """
        content = "Vorne &#167; 134 BGB Hinten"
        # Pretend offsets were stored against the decoded form
        hint = 6  # roughly where the &#167; entity starts
        markers = [
            ExpectedTextMarker(hint, hint + len("§ 134 BGB"), text="§ 134 BGB", marker_id="x")
        ]

        result = insert_markers(content, markers)

        self.assertIn("[ref=x]&#167; 134 BGB[/ref]", result)

    def test_multiple_candidates_picks_nearest_to_hint(self):
        """Same citation appearing twice: hint-distance picks the right one."""
        content = (
            "First occurrence § 25 StVG here, "
            "second occurrence § 25 StVG there."
        )
        # Two markers: one near the first occurrence, one near the second
        first_pos = content.index("§ 25 StVG")
        second_pos = content.rindex("§ 25 StVG")
        # Both stored offsets drift by -3 chars (simulating a small prefix
        # change since extraction):
        markers = [
            ExpectedTextMarker(first_pos - 3, first_pos - 3 + 9, text="§ 25 StVG", marker_id="a"),
            ExpectedTextMarker(second_pos - 3, second_pos - 3 + 9, text="§ 25 StVG", marker_id="b"),
        ]

        result = insert_markers(content, markers)

        # Both citations should be wrapped (one with each marker_id)
        self.assertIn("[ref=a]§ 25 StVG[/ref]", result)
        self.assertIn("[ref=b]§ 25 StVG[/ref]", result)

    def test_unrecoverable_marker_still_skipped(self):
        """When the citation no longer exists in content, skip (no broken anchor)."""
        content = "Some completely different text here"
        markers = [
            ExpectedTextMarker(5, 14, text="§ 25 StVG", marker_id="gone")
        ]

        result = insert_markers(content, markers)

        # Content rendered unchanged — guard preserved
        self.assertEqual(result, content)

    def test_nbsp_entity_inversion_handled(self):
        """``\\xa0`` in marker text maps to ``&#160;`` in stored content."""
        content = "Siehe &#167;&#160;130a Satz&#160;1 VwGO unten."
        # Hint near where the entity-encoded citation starts
        marker_text = "§\xa0130a Satz\xa01 VwGO"
        markers = [
            ExpectedTextMarker(0, len(marker_text), text=marker_text, marker_id="nbsp")
        ]

        result = insert_markers(content, markers)

        self.assertIn(
            "[ref=nbsp]&#167;&#160;130a Satz&#160;1 VwGO[/ref]", result
        )


@tag("lib", "markers")
class CustomMarkerFormatTestCase(TestCase):
    """Tests for custom marker formats."""

    def test_custom_html_marker(self):
        """Test a marker with HTML-style formatting."""

        class HtmlMarker(BaseMarker):
            def __init__(self, start, end, css_class="highlight"):
                self.start = start
                self.end = end
                self.css_class = css_class

            def get_start_position(self):
                return self.start

            def get_end_position(self):
                return self.end

            def get_marker_open_format(self):
                return '<span class="{css_class}">'

            def get_marker_close_format(self):
                return "</span>"

        content = "Important text here"
        marker = HtmlMarker(0, 9, css_class="important")

        result, _ = marker.insert_marker(content, 0)

        self.assertEqual(result, '<span class="important">Important</span> text here')

    def test_custom_marker_with_uuid(self):
        """Test a marker with UUID formatting."""

        class UuidMarker(BaseMarker):
            def __init__(self, start, end, uuid):
                self.start = start
                self.end = end
                self.uuid = uuid

            def get_start_position(self):
                return self.start

            def get_end_position(self):
                return self.end

            def get_marker_open_format(self):
                return '[link id="{uuid}"]'

            def get_marker_close_format(self):
                return "[/link]"

        content = "Click here"
        marker = UuidMarker(0, 5, uuid="550e8400-e29b-41d4-a716-446655440000")

        result, _ = marker.insert_marker(content, 0)

        self.assertEqual(
            result,
            '[link id="550e8400-e29b-41d4-a716-446655440000"]Click[/link] here',
        )
