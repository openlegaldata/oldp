"""Unit tests for shared MCP helpers in ``oldp.apps.mcp.utils``."""

from django.test import SimpleTestCase

from oldp.apps.mcp.utils import html_to_text, is_snippet_request, text_snippet


class HtmlToTextTests(SimpleTestCase):
    """Tests for the plain-text rendering used by snippet offsets."""

    def test_empty(self):
        self.assertEqual(html_to_text(None), "")
        self.assertEqual(html_to_text(""), "")

    def test_strips_tags_and_decodes_entities(self):
        self.assertEqual(
            html_to_text("<p>Die Kl&#228;gerin &amp; der Beklagte</p>"),
            "Die Klägerin & der Beklagte",
        )

    def test_escaped_markup_is_kept_as_text(self):
        self.assertEqual(html_to_text("<p>&lt;b&gt; bleibt</p>"), "<b> bleibt")

    def test_block_elements_become_lines_and_whitespace_collapses(self):
        value = (
            "<h2>Tenor</h2>\n<div>\n   <dl><dt/><dd>\n  <p>Satz  eins.</p>"
            "</dd></dl>\n\n\n<dl><dt/><dd><p/></dd></dl><p>Satz\tzwei.</p></div>"
        )
        self.assertEqual(html_to_text(value), "Tenor\nSatz eins.\nSatz zwei.")


class TextSnippetTests(SimpleTestCase):
    """Tests for offset/length slicing of plain text."""

    def test_is_snippet_request(self):
        self.assertFalse(is_snippet_request(0, 0))
        self.assertTrue(is_snippet_request(5, 0))
        self.assertTrue(is_snippet_request(0, 5))
        self.assertTrue(is_snippet_request(-1, 0))

    def test_slice_with_more(self):
        result = text_snippet("<p>abcdefghij</p>", offset=2, length=3)
        self.assertEqual(
            result,
            {
                "text": "cde",
                "offset": 2,
                "length": 3,
                "total_length": 10,
                "has_more": True,
                "next_offset": 5,
            },
        )

    def test_length_past_end_is_capped(self):
        result = text_snippet("<p>abcdefghij</p>", offset=8, length=100)
        self.assertEqual(result["text"], "ij")
        self.assertFalse(result["has_more"])
        self.assertIsNone(result["next_offset"])

    def test_offset_at_end_returns_empty_text(self):
        result = text_snippet("<p>abc</p>", offset=3, length=0)
        self.assertEqual(result["text"], "")
        self.assertFalse(result["has_more"])

    def test_invalid_arguments(self):
        self.assertIn("error", text_snippet("<p>abc</p>", offset=-1, length=0))
        self.assertIn("error", text_snippet("<p>abc</p>", offset=0, length=-1))
        self.assertIn("error", text_snippet("<p>abc</p>", offset=4, length=0))
