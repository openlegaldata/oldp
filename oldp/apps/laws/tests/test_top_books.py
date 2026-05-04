"""Tests for the /law/ index ordering rules.

Covers:
  * top books driven by settings.TOP_LAW_BOOKS (slug allowlist, ordered)
  * empty allowlist → top block hidden
  * unknown / whitespace-padded slugs tolerated
  * unfiltered list ordered by -updated_date
  * char-filtered (/law/<a>/, /law/0-9/) lists ordered by slug
  * pending top-listed book hidden from anon, visible to staff
  * top block suppressed on char-filtered views even if allowlist is set
"""

from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from oldp.apps.laws.models import LawBook

User = get_user_model()


def assert_order(test, body: bytes, first: bytes, second: bytes, msg: str = "") -> None:
    """Assert ``first`` appears before ``second`` in ``body``."""
    p1 = body.find(first)
    p2 = body.find(second)
    test.assertNotEqual(p1, -1, f"{first!r} not in body — {msg}")
    test.assertNotEqual(p2, -1, f"{second!r} not in body — {msg}")
    test.assertLess(p1, p2, f"{first!r} should appear before {second!r} — {msg}")


@override_settings(
    CACHES={"default": {"BACKEND": "django.core.cache.backends.dummy.DummyCache"}}
)
class LawIndexOrderingTestCase(TestCase):
    """Comprehensive coverage of the /law/ index ordering rules."""

    @classmethod
    def setUpTestData(cls):
        cls.staff = User.objects.create_user(
            username="staff", password="pass", is_staff=True
        )

        # Numeric-prefix books — used to verify /law/0-9/ slug ordering
        cls.book_1 = LawBook.objects.create(
            slug="1book",
            code="1B",
            title="One",
            order=0,
            latest=True,
            revision_date=date(2020, 1, 1),
            review_status="accepted",
        )
        cls.book_2 = LawBook.objects.create(
            slug="2book",
            code="2B",
            title="Two",
            order=0,
            latest=True,
            revision_date=date(2020, 1, 1),
            review_status="accepted",
        )
        cls.book_9 = LawBook.objects.create(
            slug="9book",
            code="9B",
            title="Nine",
            order=0,
            latest=True,
            revision_date=date(2020, 1, 1),
            review_status="accepted",
        )

        # Alpha books with deliberately *non-alphabetical* titles to make
        # sure ordering is by slug, not by the legacy title sort.
        cls.alpha_a = LawBook.objects.create(
            slug="alpha-a",
            code="ALPHA-A",
            title="Zzz title",
            order=0,
            latest=True,
            revision_date=date(2020, 1, 1),
            review_status="accepted",
        )
        cls.alpha_z = LawBook.objects.create(
            slug="alpha-z",
            code="ALPHA-Z",
            title="Aaa title",
            order=0,
            latest=True,
            revision_date=date(2020, 1, 1),
            review_status="accepted",
        )

        # Curated top-list candidates — distinguishable by code.
        cls.gg = LawBook.objects.create(
            slug="gg",
            code="GG",
            title="Grundgesetz",
            order=0,
            latest=True,
            revision_date=date(2020, 1, 1),
            review_status="accepted",
        )
        cls.bgb = LawBook.objects.create(
            slug="bgb",
            code="BGB",
            title="Bürgerliches Gesetzbuch",
            order=0,
            latest=True,
            revision_date=date(2020, 1, 1),
            review_status="accepted",
        )
        cls.stgb = LawBook.objects.create(
            slug="stgb",
            code="STGB",
            title="Strafgesetzbuch",
            order=0,
            latest=True,
            revision_date=date(2020, 1, 1),
            review_status="accepted",
        )

        # Bypass auto_now to set deterministic updated_date timestamps for
        # the date-ordering check (latest first):
        #     gg  > 1book > alpha-a > others
        now = timezone.now()
        LawBook.objects.filter(pk=cls.gg.pk).update(
            updated_date=now - timedelta(days=1)
        )
        LawBook.objects.filter(pk=cls.book_1.pk).update(
            updated_date=now - timedelta(days=2)
        )
        LawBook.objects.filter(pk=cls.alpha_a.pk).update(
            updated_date=now - timedelta(days=3)
        )
        for b in (cls.book_2, cls.book_9, cls.alpha_z, cls.bgb, cls.stgb):
            LawBook.objects.filter(pk=b.pk).update(
                updated_date=now - timedelta(days=10)
            )

    def setUp(self):
        # cache_per_role would otherwise leak responses across tests
        cache.clear()

    # --- 1. Empty allowlist → top section hidden ---

    @override_settings(TOP_LAW_BOOKS=[])
    def test_empty_allowlist_hides_top_section(self):
        res = self.client.get(reverse("laws:index"))
        self.assertEqual(res.status_code, 200)
        self.assertEqual(list(res.context["top_items"]), [])
        # Heading is wrapped by `{% if top_items %}` in the template
        self.assertNotContains(res, "More Laws")

    # --- 2. Configured allowlist → ordered top books ---

    @override_settings(TOP_LAW_BOOKS=["bgb", "gg", "stgb"])
    def test_configured_top_books_in_listed_order(self):
        res = self.client.get(reverse("laws:index"))
        self.assertEqual(res.status_code, 200)
        slugs = [b.slug for b in res.context["top_items"]]
        self.assertEqual(slugs, ["bgb", "gg", "stgb"])

        body = res.content
        assert_order(self, body, b"BGB", b"GG", "BGB before GG in HTML")
        assert_order(self, body, b"GG", b"STGB", "GG before STGB in HTML")
        # "More Laws" heading appears now that top_items is non-empty
        self.assertContains(res, "More Laws")

    # --- 3. Unknown slugs → silently dropped, no 500 ---

    @override_settings(TOP_LAW_BOOKS=["does-not-exist", "gg", "also-bogus"])
    def test_unknown_slugs_are_dropped(self):
        res = self.client.get(reverse("laws:index"))
        self.assertEqual(res.status_code, 200)
        slugs = [b.slug for b in res.context["top_items"]]
        self.assertEqual(slugs, ["gg"])

    # --- 4. Whitespace tolerance ---

    @override_settings(TOP_LAW_BOOKS=[" gg", "bgb ", "  ", ""])
    def test_whitespace_in_slugs_is_stripped(self):
        res = self.client.get(reverse("laws:index"))
        self.assertEqual(res.status_code, 200)
        slugs = [b.slug for b in res.context["top_items"]]
        self.assertEqual(slugs, ["gg", "bgb"])

    # --- 5. Main list ordered by -updated_date ---

    @override_settings(TOP_LAW_BOOKS=[])
    def test_main_list_ordered_by_updated_date_desc(self):
        res = self.client.get(reverse("laws:index"))
        items = list(res.context["items"].object_list)
        # gg (1d ago) → 1book (2d) → alpha-a (3d) → tied 10d-ago group
        first_three = [b.slug for b in items[:3]]
        self.assertEqual(first_three, ["gg", "1book", "alpha-a"])

    # --- 6. /law/<char>/ ordered by slug, not title ---

    @override_settings(TOP_LAW_BOOKS=["gg", "bgb"])
    def test_alpha_filter_orders_by_slug_not_title(self):
        res = self.client.get(reverse("laws:index_char", args=("a",)))
        self.assertEqual(res.status_code, 200)
        items = list(res.context["items"].object_list)
        slugs = [b.slug for b in items]
        # alpha-a (titled "Zzz") MUST come before alpha-z (titled "Aaa")
        self.assertEqual(slugs, ["alpha-a", "alpha-z"])
        # No top block on char filters even with allowlist populated
        self.assertEqual(list(res.context["top_items"]), [])

    # --- 7. /law/0-9/ ordered by slug ---

    @override_settings(TOP_LAW_BOOKS=["gg"])
    def test_digit_filter_orders_by_slug(self):
        res = self.client.get(reverse("laws:index_char", args=("0-9",)))
        self.assertEqual(res.status_code, 200)
        items = list(res.context["items"].object_list)
        self.assertEqual([b.slug for b in items], ["1book", "2book", "9book"])
        self.assertEqual(list(res.context["top_items"]), [])

    # --- 8. Top section respects review_status visibility ---

    @override_settings(TOP_LAW_BOOKS=["gg", "bgb"])
    def test_pending_top_book_hidden_from_anon(self):
        LawBook.objects.filter(pk=self.gg.pk).update(review_status="pending")
        res = self.client.get(reverse("laws:index"))
        slugs = [b.slug for b in res.context["top_items"]]
        self.assertEqual(slugs, ["bgb"])  # gg dropped from top for anon

    @override_settings(TOP_LAW_BOOKS=["gg", "bgb"])
    def test_pending_top_book_visible_to_staff(self):
        LawBook.objects.filter(pk=self.gg.pk).update(review_status="pending")
        self.client.force_login(self.staff)
        res = self.client.get(reverse("laws:index"))
        slugs = [b.slug for b in res.context["top_items"]]
        self.assertEqual(slugs, ["gg", "bgb"])

    # --- 9. Char filters never render the top block ---

    @override_settings(TOP_LAW_BOOKS=["gg", "bgb", "stgb"])
    def test_top_block_absent_on_alpha_filter_even_with_allowlist(self):
        res = self.client.get(reverse("laws:index_char", args=("g",)))
        self.assertEqual(list(res.context["top_items"]), [])

    @override_settings(TOP_LAW_BOOKS=["gg", "bgb", "stgb"])
    def test_top_block_absent_on_digit_filter_even_with_allowlist(self):
        res = self.client.get(reverse("laws:index_char", args=("0-9",)))
        self.assertEqual(list(res.context["top_items"]), [])
