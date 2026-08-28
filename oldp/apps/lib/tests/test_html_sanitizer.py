"""Tests for the ingested-content HTML sanitizer."""

from django.template import Context, Template
from django.test import SimpleTestCase
from django.utils.safestring import SafeString

from oldp.apps.lib.html_sanitizer import sanitize_html
from oldp.apps.lib.templatetags.html_filters import sanitize_html as sanitize_filter


class SanitizeHtmlTest(SimpleTestCase):
    # --- strips script execution vectors ---

    def test_strips_script_tag(self):
        self.assertNotIn("<script", sanitize_html("<p>ok</p><script>alert(1)</script>"))

    def test_strips_event_handler(self):
        out = sanitize_html('<img src=x onerror="alert(1)">')
        self.assertNotIn("onerror", out)
        self.assertNotIn("<img", out)  # img not on the allowlist

    def test_strips_anchor_onclick(self):
        out = sanitize_html('<a href="/x" onclick="evil()">link</a>')
        self.assertNotIn("onclick", out)
        self.assertIn("link", out)

    def test_strips_javascript_url(self):
        out = sanitize_html('<a href="javascript:alert(1)">x</a>')
        self.assertNotIn("javascript:", out)

    def test_strips_iframe_and_style_tag(self):
        out = sanitize_html("<iframe src=//evil></iframe><style>*{x:y}</style><p>t</p>")
        self.assertNotIn("<iframe", out)
        self.assertNotIn("<style", out)
        self.assertIn("<p>t</p>", out)

    # --- preserves legitimate legal-document markup ---

    def test_keeps_structural_markup(self):
        html = (
            "<h2>Tenor</h2><p>Text</p>"
            "<table><thead><tr><th>A</th></tr></thead>"
            "<tbody><tr><td colspan='2'>B</td></tr></tbody></table>"
            "<ol><li>x</li></ol><blockquote>q</blockquote>"
        )
        out = sanitize_html(html)
        for frag in ("<h2>", "<table>", "<th>", 'colspan="2"', "<ol>", "<blockquote>"):
            self.assertIn(frag, out)

    def test_keeps_relative_and_fragment_hrefs(self):
        out = sanitize_html('<a href="/case/123">c</a><a href="#refs">r</a>')
        self.assertIn('href="/case/123"', out)
        self.assertIn('href="#refs"', out)

    # --- preserves the trusted marker markup, drops unsafe style ---

    def test_keeps_reference_marker_anchor(self):
        html = '<a href="#refs" data-marker-id="abc-1" class="ref">§ 1</a>'
        out = sanitize_html(html)
        self.assertIn('data-marker-id="abc-1"', out)
        self.assertIn('class="ref"', out)
        self.assertIn('href="#refs"', out)

    def test_keeps_annotation_background_color_only(self):
        html = '<span class="marker" style="background-color: #ff0000">x</span>'
        self.assertIn("background-color", sanitize_html(html))

    def test_strips_dangerous_style_properties(self):
        html = '<span style="position: fixed; top: 0; background-color: red">x</span>'
        out = sanitize_html(html)
        self.assertNotIn("position", out)
        self.assertNotIn("fixed", out)
        self.assertIn("background-color", out)

    def test_empty_input_unchanged(self):
        self.assertEqual(sanitize_html(""), "")
        self.assertEqual(sanitize_html(None), None)

    def test_mark_then_sanitize_pipeline(self):
        """Real render order: insert reference markers, then sanitize the final
        HTML. The trusted marker anchor survives; an injected <script> does not.
        """
        from oldp.apps.references.models import ReferenceMarker

        raw = "See [ref=abc-1]§ 1 BGB[/ref]<script>alert(1)</script> here"
        marked = ReferenceMarker.make_markers_clickable(raw)
        out = sanitize_html(marked)

        self.assertIn('data-marker-id="abc-1"', out)
        self.assertIn('class="ref"', out)
        self.assertIn("§ 1 BGB", out)
        self.assertNotIn("<script", out)
        self.assertNotIn("onclick", out)


class SanitizeHtmlFilterTest(SimpleTestCase):
    def test_filter_returns_safe_string(self):
        self.assertIsInstance(sanitize_filter("<p>x</p>"), SafeString)

    def test_filter_in_template_strips_script(self):
        tpl = Template("{% load html_filters %}{{ body|sanitize_html }}")
        rendered = tpl.render(Context({"body": "<p>hi</p><script>alert(1)</script>"}))
        self.assertIn("<p>hi</p>", rendered)
        self.assertNotIn("<script", rendered)

    def test_filter_does_not_double_escape(self):
        tpl = Template("{% load html_filters %}{{ body|sanitize_html }}")
        rendered = tpl.render(Context({"body": "<p>a &amp; b</p>"}))
        self.assertNotIn("&amp;amp;", rendered)
