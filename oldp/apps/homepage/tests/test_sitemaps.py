import re
import tempfile
from datetime import date
from io import StringIO
from pathlib import Path
from unittest import mock

from django.contrib.sites.models import Site
from django.core.management import call_command
from django.test import TestCase, override_settings, tag

from oldp.apps.cases.models import Case
from oldp.apps.cases.sitemaps import CaseSitemap
from oldp.apps.courts.models import Court
from oldp.apps.laws.models import Law, LawBook
from oldp.apps.lib.sitemaps import generate_sitemaps


@tag("views")
class SitemapTestCase(TestCase):
    fixtures = [
        "locations/countries.json",
        "locations/states.json",
        "locations/cities.json",
        "courts/courts.json",
    ]

    @classmethod
    def setUpTestData(cls):
        Site.objects.filter(pk=1).update(domain="de.example.org")
        court = Court.objects.exclude(pk=Court.DEFAULT_ID).first()
        cls.cases = [
            Case.objects.create(
                court=court,
                file_number=f"SITEMAP {i}/26",
                slug=f"sitemap-{i}-26",
                date=date(2026, 1, 1),
                content="<p>Text</p>",
            )
            for i in range(3)
        ]
        Case.objects.create(
            court=court,
            file_number="PENDING 1/26",
            slug="pending-1-26",
            date=date(2026, 1, 1),
            content="<p>Text</p>",
            review_status="pending",
        )
        book = LawBook.objects.create(
            code="SMG",
            title="Sitemapgesetz",
            slug="smg",
            revision_date=date(2024, 1, 1),
            latest=True,
        )
        cls.law = Law.objects.create(book=book, slug="1", title="§ 1", content="x")

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        settings = override_settings(SITEMAP_ROOT=self.root)
        settings.enable()
        self.addCleanup(settings.disable)

    def read(self, name):
        return (self.root / name).read_text(encoding="utf-8")

    def locs(self, name):
        return re.findall(r"<loc>([^<]+)</loc>", self.read(name))

    def test_generates_index_and_pages(self):
        summary = generate_sitemaps()

        self.assertEqual(summary["case"], (3, 1))
        self.assertEqual(summary["law"], (1, 1))
        self.assertEqual(
            self.locs("sitemap.xml"),
            [
                "https://de.example.org/sitemap-court-1.xml",
                "https://de.example.org/sitemap-case-1.xml",
                "https://de.example.org/sitemap-law-1.xml",
            ],
        )
        self.assertIn("<lastmod>", self.read("sitemap.xml"))
        case_locs = self.locs("sitemap-case-1.xml")
        self.assertEqual(
            case_locs,
            [f"https://de.example.org/case/sitemap-{i}-26" for i in range(3)],
        )
        self.assertEqual(
            self.locs("sitemap-law-1.xml"), ["https://de.example.org/law/smg/1"]
        )
        self.assertTrue(self.locs("sitemap-court-1.xml"))

    def test_pending_cases_are_left_out(self):
        generate_sitemaps()

        self.assertNotIn("pending-1-26", self.read("sitemap-case-1.xml"))

    def test_splits_pages_and_removes_stale_ones(self):
        with mock.patch.object(CaseSitemap, "limit", 1):
            summary = generate_sitemaps()
        self.assertEqual(summary["case"], (3, 3))
        self.assertTrue((self.root / "sitemap-case-3.xml").is_file())
        self.assertIn(
            "https://de.example.org/sitemap-case-3.xml", self.locs("sitemap.xml")
        )

        # A later run with fewer pages deletes the pages it no longer writes.
        generate_sitemaps()
        self.assertFalse((self.root / "sitemap-case-2.xml").exists())
        self.assertFalse((self.root / "sitemap-case-3.xml").exists())
        self.assertEqual(len(self.locs("sitemap-case-1.xml")), 3)

    def test_view_serves_generated_files(self):
        self.assertEqual(self.client.get("/sitemap.xml").status_code, 404)

        generate_sitemaps()
        for path in ("/sitemap.xml", "/sitemap-case-1.xml"):
            res = self.client.get(path)
            self.assertEqual(res.status_code, 200, path)
            self.assertEqual(res["Content-Type"], "application/xml")
            self.assertIn("Last-Modified", res)
            self.assertEqual(
                b"".join(res.streaming_content).decode(), self.read(path[1:])
            )
        self.assertEqual(self.client.get("/sitemap-case-9.xml").status_code, 404)

    def test_command(self):
        out = StringIO()
        call_command("generate_sitemaps", stdout=out)

        self.assertIn("case: 3 items in 1 page(s)", out.getvalue())
        self.assertTrue((self.root / "sitemap.xml").is_file())
