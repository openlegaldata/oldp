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

        result = insert_markers(content, markers)

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
