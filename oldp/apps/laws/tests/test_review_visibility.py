"""Tests for review_status visibility on laws HTML views and Law.get_title()."""

from datetime import date

from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse

from oldp.apps.laws.models import Law, LawBook

User = get_user_model()


@override_settings(
    CACHES={"default": {"BACKEND": "django.core.cache.backends.dummy.DummyCache"}}
)
class LawsReviewVisibilityTestCase(TestCase):
    """End-to-end visibility checks for /law/, /law/<book>/, /law/<book>/<sec>."""

    @classmethod
    def setUpTestData(cls):
        cls.factory = RequestFactory()
        cls.staff = User.objects.create_user(
            username="staff", password="pass", is_staff=True
        )
        cls.regular = User.objects.create_user(username="reg", password="pass")

        cls.book_acc = LawBook.objects.create(
            slug="acc-book",
            code="ACC",
            title="Accepted book",
            order=1,
            latest=True,
            revision_date=date(2026, 1, 1),
            review_status="accepted",
        )
        cls.book_pending = LawBook.objects.create(
            slug="pend-book",
            code="PEND",
            title="Pending book",
            order=2,
            latest=True,
            revision_date=date(2026, 1, 1),
            review_status="pending",
        )

        cls.law_acc = Law.objects.create(
            book=cls.book_acc,
            slug="art-1",
            section="Art 1",
            title="Würde des Menschen",
            order=10,
            review_status="accepted",
        )
        cls.law_pending = Law.objects.create(
            book=cls.book_acc,
            slug="art-2",
            section="Art 2",
            title="Persönliche Freiheit",
            order=20,
            review_status="pending",
        )

    # --- Static method behaviour --------------------------------------

    def test_lawbook_get_queryset_anon_hides_pending(self):
        qs = LawBook.get_queryset()
        self.assertIn(self.book_acc, qs)
        self.assertNotIn(self.book_pending, qs)

    def test_lawbook_get_queryset_staff_shows_all(self):
        req = self.factory.get("/")
        req.user = self.staff
        qs = LawBook.get_queryset(req)
        self.assertIn(self.book_acc, qs)
        self.assertIn(self.book_pending, qs)

    def test_law_get_queryset_anon_hides_pending(self):
        qs = Law.get_queryset()
        self.assertIn(self.law_acc, qs)
        self.assertNotIn(self.law_pending, qs)

    def test_law_get_queryset_staff_shows_all(self):
        req = self.factory.get("/")
        req.user = self.staff
        qs = Law.get_queryset(req)
        self.assertIn(self.law_acc, qs)
        self.assertIn(self.law_pending, qs)

    # --- View-level integration ---------------------------------------

    def test_index_anon_excludes_pending_book(self):
        res = self.client.get(reverse("laws:index"))
        self.assertContains(res, "Accepted book")
        self.assertNotContains(res, "Pending book")

    def test_index_staff_includes_pending_book(self):
        self.client.force_login(self.staff)
        res = self.client.get(reverse("laws:index"))
        self.assertContains(res, "Accepted book")
        self.assertContains(res, "Pending book")

    def test_book_detail_anon_404s_on_pending_book(self):
        res = self.client.get(reverse("laws:book", args=("pend-book",)))
        self.assertEqual(res.status_code, 404)

    def test_book_detail_staff_renders_pending_book(self):
        self.client.force_login(self.staff)
        res = self.client.get(reverse("laws:book", args=("pend-book",)))
        self.assertEqual(res.status_code, 200)

    def test_law_detail_anon_omits_pending_section(self):
        # Section list within the accepted book should hide the pending law
        res = self.client.get(reverse("laws:book", args=("acc-book",)))
        self.assertContains(res, "Würde des Menschen")
        self.assertNotContains(res, "Persönliche Freiheit")

    def test_law_detail_anon_404s_on_pending_law(self):
        res = self.client.get(reverse("laws:law", args=("acc-book", "art-2")))
        self.assertEqual(res.status_code, 404)

    def test_law_detail_staff_renders_pending_law(self):
        self.client.force_login(self.staff)
        res = self.client.get(reverse("laws:law", args=("acc-book", "art-2")))
        self.assertEqual(res.status_code, 200)


class LawGetTitleDedupTestCase(TestCase):
    """Bug 2: get_title must not render '§ 13 § 13' when title == section."""

    @classmethod
    def setUpTestData(cls):
        cls.book = LawBook.objects.create(
            slug="bgb",
            code="BGB",
            title="Bürgerliches Gesetzbuch",
            order=1,
            latest=True,
            revision_date=date(2026, 1, 1),
            review_status="accepted",
        )

    def _make(self, slug, section, title):
        return Law(book=self.book, slug=slug, section=section, title=title, order=1)

    def test_distinct_title_is_kept(self):
        law = self._make("p1", "§ 1", "Beginn der Rechtsfähigkeit")
        self.assertEqual(law.get_title(), "BGB § 1 Beginn der Rechtsfähigkeit")

    def test_title_equals_section_is_deduped(self):
        law = self._make("p13", "§ 13", "§ 13")
        self.assertEqual(law.get_title(), "BGB § 13")

    def test_empty_title_renders_section_only(self):
        law = self._make("p7", "§ 7", "")
        self.assertEqual(law.get_title(), "BGB § 7")

    def test_whitespace_only_title_renders_section_only(self):
        law = self._make("p8", "§ 8", "   ")
        self.assertEqual(law.get_title(), "BGB § 8")

    def test_title_with_padding_still_dedupes(self):
        law = self._make("p9", "§ 9", " § 9 ")
        self.assertEqual(law.get_title(), "BGB § 9")
