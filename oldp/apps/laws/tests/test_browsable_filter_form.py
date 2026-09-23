"""The browsable API must not render one ``<option>`` per law book.

``filterset_fields = ("book_id", ...)`` let django-filter auto-generate a
``ModelChoiceFilter`` for the ``book`` FK. The browsable renderer turns that
into a ``<select>`` over the whole ``LawBook`` table -- ~10,000 options on
prod, 1.5 MB of HTML and ~1.7s per request, paid identically by a
``?limit=1`` request because the form has nothing to do with the result set.

This is the last open item of the citing-endpoint performance work: the
``?format=api`` variants stayed ~15x slower than JSON long after the queries
themselves were fixed, and this form was the whole remaining difference.
"""

from django.test import TestCase, override_settings

from oldp.apps.laws.models import Law, LawBook

NO_CACHE = {"default": {"BACKEND": "django.core.cache.backends.dummy.DummyCache"}}


@override_settings(CACHES=NO_CACHE)
class LawBrowsableFilterFormTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        for i in range(25):
            book = LawBook.objects.create(
                code=f"B{i}",
                title=f"Book {i}",
                slug=f"book-{i}",
                latest=True,
                revision_date="2024-01-01",
                review_status="accepted",
            )
            Law.objects.create(
                book=book, section=f"§ {i}", slug=str(i), review_status="accepted"
            )

    def test_filter_form_does_not_enumerate_law_books(self):
        res = self.client.get("/api/laws/?format=api")

        self.assertEqual(res.status_code, 200)
        html = res.content.decode()
        # One <select> per boolean filter is fine; what must not happen is the
        # option count scaling with the number of books.
        self.assertLess(
            html.count("<option"),
            LawBook.objects.count(),
            msg="filter form is still enumerating law books",
        )

    def test_book_id_filter_still_works(self):
        book = LawBook.objects.get(slug="book-3")

        res = self.client.get(f"/api/laws/?book_id={book.pk}")

        self.assertEqual(res.status_code, 200)
        results = res.json()["results"]
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["slug"], "3")

    def test_remaining_book_filters_still_work(self):
        res = self.client.get("/api/laws/?book__slug=book-7&book__latest=true")

        self.assertEqual(res.status_code, 200)
        self.assertEqual(len(res.json()["results"]), 1)

    def test_unknown_book_id_returns_empty_not_error(self):
        res = self.client.get("/api/laws/?book_id=99999999")

        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["results"], [])
