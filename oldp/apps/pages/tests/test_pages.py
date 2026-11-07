import tempfile
from pathlib import Path

from django.contrib.flatpages.models import FlatPage
from django.contrib.sites.models import Site
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import translation
from django.utils.safestring import SafeString

import oldp
from oldp.apps.pages import renderer
from oldp.apps.pages.renderer import PageNotFound, render_page
from oldp.apps.pages.variables import page_variables


class MarkdownPageViewTest(TestCase):
    """The shipped default content (imprint/privacy/terms) renders at /pages/."""

    def test_url_reverses(self):
        self.assertEqual(
            reverse("markdown_page", kwargs={"slug": "imprint"}), "/pages/imprint/"
        )

    def test_renders_markdown_page(self):
        res = self.client.get("/pages/privacy/")
        self.assertEqual(res.status_code, 200)
        self.assertTemplateUsed(res, "pages/detail.html")
        self.assertContains(res, "<h1")
        self.assertContains(res, "Privacy Policy")  # from the title: meta / H1

    def test_each_default_page_renders(self):
        for slug in ("imprint", "privacy", "terms"):
            with self.subTest(slug=slug):
                self.assertEqual(self.client.get(f"/pages/{slug}/").status_code, 200)


class FallbackTest(TestCase):
    """Unknown slugs fall back to DB flatpages, then 404."""

    def test_falls_back_to_flatpage(self):
        fp = FlatPage.objects.create(
            url="/about-us/", title="About", content="<p>Hello flatpage</p>"
        )
        fp.sites.add(Site.objects.get_current())
        res = self.client.get("/pages/about-us/")
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "Hello flatpage")

    def test_unknown_slug_404(self):
        self.assertEqual(self.client.get("/pages/does-not-exist/").status_code, 404)


class LegacyRedirectTest(TestCase):
    """Old bare flatpage URLs 301 to the new /pages/<slug>/ routes."""

    def test_legacy_urls_redirect(self):
        for slug in ("imprint", "privacy", "terms"):
            with self.subTest(slug=slug):
                res = self.client.get(f"/{slug}/")
                self.assertEqual(res.status_code, 301)
                self.assertEqual(res["Location"], f"/pages/{slug}/")


class RendererTest(TestCase):
    def test_render_page_returns_safe_html_and_title(self):
        page = render_page("terms")
        self.assertEqual(page["slug"], "terms")
        self.assertIsInstance(page["html"], SafeString)
        self.assertIn("<h1", page["html"])
        self.assertTrue(page["title"])

    def test_missing_file_raises(self):
        with self.assertRaises(PageNotFound):
            render_page("nope-not-here")

    def test_traversal_attempt_raises(self):
        for bad in ("../secrets", "foo/bar", "a.b"):
            with self.subTest(bad=bad):
                with self.assertRaises(PageNotFound):
                    render_page(bad)

    def test_cache_is_mtime_keyed(self):
        """A file is parsed once, then re-parsed only when its mtime changes."""
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "demo.md"
            f.write_text("title: One\n\n# One\n", encoding="utf-8")
            with override_settings(MARKDOWN_PAGES_DIR=d):
                renderer._render.cache_clear()
                first = render_page("demo")
                self.assertEqual(first["title"], "One")
                hits_before = renderer._render.cache_info().hits
                render_page("demo")  # served from cache, same mtime
                self.assertEqual(renderer._render.cache_info().hits, hits_before + 1)

                # Edit the file with a newer mtime -> cache invalidated, re-rendered
                import os

                f.write_text("title: Two\n\n# Two\n", encoding="utf-8")
                os.utime(f, (f.stat().st_atime + 10, f.stat().st_mtime + 10))
                self.assertEqual(render_page("demo")["title"], "Two")


class PageVariablesTest(TestCase):
    """``{{ key }}`` placeholders are filled from settings at render time."""

    REST = {
        "DEFAULT_THROTTLE_RATES": {
            "anon": "100/day",
            "user": "5000/hour",
            "enriched": "10000/hour",
        }
    }

    def _render(self, text, **extra_settings):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "demo.md").write_text(text, encoding="utf-8")
            with override_settings(MARKDOWN_PAGES_DIR=d, **extra_settings):
                renderer._render.cache_clear()
                return render_page("demo")

    def test_rate_limit_placeholders(self):
        page = self._render(
            "# Limits\n\n{{ limits.anon.count }} per {{ limits.anon.period }}, "
            "{{limits.user.count}} per {{ limits.user.period }}, "
            "MCP {{ limits.mcp_anon.raw }}\n",
            REST_FRAMEWORK=self.REST,
            MCP_ANTHROPIC_ANON_RATE="500/hour",
        )
        self.assertIn("100 per day, 5,000 per hour, MCP 500/hour", page["html"])
        self.assertNotIn("{{", page["html"])

    def test_values_follow_settings(self):
        rest = {"DEFAULT_THROTTLE_RATES": {"user": "7500/hour"}}
        page = self._render("{{ limits.user.count }}\n", REST_FRAMEWORK=rest)
        self.assertIn("7,500", page["html"])

    def test_german_formatting(self):
        with translation.override("de"):
            page = self._render(
                "{{ limits.user.count }} pro {{ limits.user.period }}\n",
                REST_FRAMEWORK=self.REST,
            )
            # "Stunde" once messages are compiled (Docker image); the test venv
            # may run without .mo files, so compare against gettext directly.
            hour = translation.gettext("hour")
        self.assertIn(f"5.000 pro {hour}", page["html"])

    def test_url_placeholders(self):
        page = self._render(
            "`{{ urls.mcp }}` and {{ urls.whoami }}\n",
            SITE_URL="https://example.org/",
        )
        self.assertIn("<code>https://example.org/mcp</code>", page["html"])
        self.assertIn("https://example.org/api/whoami/", page["html"])

    def test_title_placeholder(self):
        page = self._render("title: OLDP {{ version }}\n\nBody\n")
        self.assertEqual(page["title"], f"OLDP {oldp.__version__}")

    def test_unknown_key_left_visible_and_logged(self):
        with self.assertLogs("oldp.apps.pages.variables", level="WARNING") as logs:
            page = self._render("# T\n\nValue: {{ limits.nope.count }}\n")
        self.assertIn("{{ limits.nope.count }}", page["html"])
        self.assertIn("limits.nope.count", logs.output[0])

    def test_values_are_html_escaped(self):
        page = self._render(
            "{{ urls.site }}\n", SITE_URL='https://example.org/"><script>'
        )
        self.assertNotIn("<script>", page["html"])
        self.assertIn("&lt;script&gt;", page["html"])

    def test_page_without_placeholders_is_untouched(self):
        renderer._render.cache_clear()
        page = render_page("terms")
        self.assertIs(page, render_page("terms"))  # cached dict returned as is

    def test_malformed_rate_is_skipped(self):
        rest = {"DEFAULT_THROTTLE_RATES": {"user": "lots"}}
        with self.assertLogs("oldp.apps.pages.variables", level="WARNING"):
            with override_settings(REST_FRAMEWORK=rest):
                variables = page_variables()
        self.assertNotIn("limits.user.count", variables)

    def test_view_renders_filled_page(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "demo.md").write_text(
                "# API\n\nLimit: {{ limits.user.count }}\n", encoding="utf-8"
            )
            with override_settings(MARKDOWN_PAGES_DIR=d, REST_FRAMEWORK=self.REST):
                renderer._render.cache_clear()
                res = self.client.get("/pages/demo/")
        self.assertContains(res, "Limit: 5,000")
