"""The case detail cache must stay small and serve warm renders cheaply.

The shared ``case_data`` entry used to hold the case with its full text, raw
crawler HTML and every cited case and law section loaded with *their* texts:
~300 KB on average, up to 11 MB. Under the shared LRU budget those entries
evicted everything else. Warm renders also paid one query per reference for
the court or law book the cached targets were missing.
"""

import pickle
from datetime import date

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from oldp.apps.cases.cache import CASE_DATA_KEY
from oldp.apps.cases.models import Case
from oldp.apps.courts.models import Court
from oldp.apps.laws.models import Law, LawBook
from oldp.apps.references.models import CaseReferenceMarker, Reference

User = get_user_model()

BIG_TEXT = "<p>" + "Lorem ipsum dolor sit amet. " * 4000 + "</p>"


@override_settings(
    CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
)
class CaseDetailCacheTestCase(TestCase):
    fixtures = [
        "locations/countries.json",
        "locations/states.json",
        "locations/cities.json",
        "courts/courts.json",
    ]

    @classmethod
    def setUpTestData(cls):
        cls.courts = list(Court.objects.exclude(pk=Court.DEFAULT_ID)[:6])
        cls.case = Case.objects.create(
            court=cls.courts[0],
            file_number="CACHE 1/26",
            slug="cache-1-26",
            date=date(2026, 1, 1),
            content="<p>Siehe § 1 ABC und BGH, Urteil vom 1.1.2020 - I ZR 1/20.</p>"
            + BIG_TEXT,
            raw=BIG_TEXT,
            abstract=BIG_TEXT,
        )
        cls.user = User.objects.create_user(username="member", password="pass")

    def setUp(self):
        cache.clear()

    def cite(self, n, first=0):
        """Attach ``n`` references to cases, ``n`` to laws and one unassigned."""
        marker = CaseReferenceMarker.objects.create(
            referenced_by=self.case, text="§ 1 ABC", start=10, end=17
        )
        refs = [self.reference(to="unbekannt 1/99")]
        for i in range(first, first + n):
            book = LawBook.objects.create(
                code=f"B{i}",
                title=f"Book {i}",
                slug=f"b{i}",
                revision_date=date(2024, 1, 1),
                latest=True,
                sections=BIG_TEXT,
            )
            law = Law.objects.create(
                book=book, title="", slug="1", section="§ 1", content=BIG_TEXT
            )
            cited = Case.objects.create(
                court=self.courts[i % len(self.courts)],
                file_number=f"CITED {i}/20",
                slug=f"cited-{i}-20",
                date=date(2020, 1, 1),
                content=BIG_TEXT,
                raw=BIG_TEXT,
            )
            refs.append(self.reference(to=f"§ 1 B{i}", law=law))
            refs.append(self.reference(to=f"CITED {i}/20", case=cited))
        marker.references.add(*refs)

    @staticmethod
    def reference(**fields):
        ref = Reference(**fields)
        ref.set_to_hash()
        ref.save()
        return ref

    def get(self):
        res = self.client.get(reverse("cases:case", args=(self.case.slug,)))
        self.assertEqual(res.status_code, 200)
        return res

    def warm_queries(self):
        self.get()
        with CaptureQueriesContext(connection) as ctx:
            self.get()
        return len(ctx.captured_queries)

    def test_cached_entry_holds_no_texts(self):
        self.cite(5)
        self.get()
        item, _ = cache.get(CASE_DATA_KEY % self.case.slug)

        for field in ("content", "raw", "abstract"):
            self.assertNotIn(field, item.__dict__, field)
        targets = [
            ref.law or ref.case for ref in item.references if ref.law or ref.case
        ]
        self.assertEqual(len(targets), 10)
        for target in targets:
            self.assertNotIn("content", target.__dict__)
        # 11 referenced objects plus the case, each with ~110 KB of text.
        self.assertLess(len(pickle.dumps((item, _))), 50_000)

    def test_warm_render_cost_does_not_grow_with_references(self):
        self.cite(1)
        few = self.warm_queries()

        Reference.objects.all().delete()
        CaseReferenceMarker.objects.all().delete()
        cache.clear()
        self.cite(6, first=1)
        many = self.warm_queries()

        self.assertEqual(few, many)

    def test_pages_render_content_and_reference_titles(self):
        self.cite(2)
        for logged_in in (False, True):
            with self.subTest(logged_in=logged_in):
                if logged_in:
                    self.client.force_login(self.user)
                cache.clear()
                for _ in range(2):  # cold, then warm
                    html = self.get().content.decode()
                    self.assertIn("Lorem ipsum dolor sit amet.", html)
                    self.assertIn("B1 § 1", html)
                    self.assertIn("CITED 1/20", html)
                    self.assertIn("/law/b1/1", html)
                    # Unassigned: a search link built from the stored text.
                    self.assertIn("/search/?q=unbekannt%201/99", html)
