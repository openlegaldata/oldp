import tempfile
from pathlib import Path

from django.contrib.flatpages.models import FlatPage
from django.contrib.sites.models import Site
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils.safestring import SafeString

from oldp.apps.pages import renderer
from oldp.apps.pages.renderer import PageNotFound, render_page


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
