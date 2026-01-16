"""Comprehensive tests for law versions/revisions functionality."""
import datetime
from unittest import skipUnless

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.test import TestCase, TransactionTestCase
from django.urls import reverse

from oldp.apps.laws.models import Law, LawBook


class LawBookRevisionModelTest(TestCase):
    """Test LawBook revision model functionality."""

    def setUp(self):
        """Create test lawbooks with different revisions."""
        self.book_v1 = LawBook.objects.create(
            code="TestGB",
            title="Test Gesetzbuch",
            slug="testgb",
            revision_date=datetime.date(2010, 1, 1),
            latest=False,
        )
        self.book_v2 = LawBook.objects.create(
            code="TestGB",
            title="Test Gesetzbuch",
            slug="testgb",
            revision_date=datetime.date(2015, 6, 15),
            latest=False,
        )
        self.book_v3 = LawBook.objects.create(
            code="TestGB",
            title="Test Gesetzbuch",
            slug="testgb",
            revision_date=datetime.date(2020, 12, 31),
            latest=True,
        )

    def test_get_revision_dates(self):
        """Test that get_revision_dates returns dates in descending order."""
        dates = self.book_v1.get_revision_dates()
        self.assertEqual(len(dates), 3)
        self.assertEqual(dates[0], datetime.date(2020, 12, 31))
        self.assertEqual(dates[1], datetime.date(2015, 6, 15))
        self.assertEqual(dates[2], datetime.date(2010, 1, 1))

    def test_get_revision_dates_with_limit(self):
        """Test get_revision_dates with limit parameter."""
        dates = self.book_v1.get_revision_dates(limit=2)
        self.assertEqual(len(dates), 2)
        self.assertEqual(dates[0], datetime.date(2020, 12, 31))
        self.assertEqual(dates[1], datetime.date(2015, 6, 15))

    def test_unique_constraint_slug_revision_date(self):
        """Test that (slug, revision_date) must be unique."""
        with self.assertRaises(Exception):  # IntegrityError
            LawBook.objects.create(
                code="TestGB",
                title="Test Gesetzbuch",
                slug="testgb",
                revision_date=datetime.date(2020, 12, 31),  # Duplicate
                latest=False,
            )

    def test_only_one_latest_per_code_validation(self):
        """Test that only one book per code can be marked as latest."""
        # Try to create another latest=True book with same code
        duplicate_latest = LawBook(
            code="TestGB",
            title="Test Gesetzbuch",
            slug="testgb2",  # Different slug
            revision_date=datetime.date(2021, 1, 1),
            latest=True,
        )
        with self.assertRaises(ValidationError) as cm:
            duplicate_latest.full_clean()
        self.assertIn("latest", cm.exception.message_dict)

    def test_revision_date_not_in_future(self):
        """Test that revision_date cannot be in the future."""
        future_book = LawBook(
            code="FutureGB",
            title="Future Gesetzbuch",
            slug="futuregb",
            revision_date=datetime.date(2099, 12, 31),
            latest=True,
        )
        with self.assertRaises(ValidationError):
            future_book.full_clean()

    def test_revision_date_not_too_old(self):
        """Test that revision_date cannot be unreasonably old."""
        ancient_book = LawBook(
            code="AncientGB",
            title="Ancient Gesetzbuch",
            slug="ancientgb",
            revision_date=datetime.date(1700, 1, 1),
            latest=True,
        )
        with self.assertRaises(ValidationError):
            ancient_book.full_clean()

    def test_get_sections_no_mutation(self):
        """Test that get_sections doesn't mutate database state."""
        book = LawBook.objects.create(
            code="SectionGB",
            title="Section Test",
            slug="sectiongb",
            sections='{"1": "Section One", "2": "Section Two"}',
            latest=True,
        )
        # Get sections (which parses JSON)
        sections = book.get_sections()
        self.assertEqual(sections["1"], "Section One")

        # Reload from database and verify sections is still a string
        book.refresh_from_db()
        self.assertIsInstance(book.sections, str)

    def test_get_changelog_no_mutation(self):
        """Test that get_changelog doesn't mutate database state."""
        book = LawBook.objects.create(
            code="ChangelogGB",
            title="Changelog Test",
            slug="changeloggb",
            changelog='[{"type": "Stand", "text": "Test change"}]',
            latest=True,
        )
        # Get changelog (which parses JSON)
        changelog = book.get_changelog()
        self.assertEqual(len(changelog), 1)

        # Reload from database and verify changelog is still a string
        book.refresh_from_db()
        self.assertIsInstance(book.changelog, str)


class LawRevisionModelTest(TestCase):
    """Test Law model revision-related functionality."""

    def setUp(self):
        """Create test laws in different revisions."""
        # Create two revisions of a lawbook
        self.book_old = LawBook.objects.create(
            code="TestGB",
            title="Test Gesetzbuch",
            slug="testgb",
            revision_date=datetime.date(2010, 1, 1),
            latest=False,
        )
        self.book_new = LawBook.objects.create(
            code="TestGB",
            title="Test Gesetzbuch",
            slug="testgb",
            revision_date=datetime.date(2020, 1, 1),
            latest=True,
        )

        # Create laws in old revision
        self.law1_old = Law.objects.create(
            book=self.book_old,
            slug="artikel-1",
            section="Art. 1",
            title="Article One",
            order=1,
        )
        self.law2_old = Law.objects.create(
            book=self.book_old,
            slug="artikel-2",
            section="Art. 2",
            title="Article Two",
            order=2,
            previous=self.law1_old,
        )
        self.law3_old = Law.objects.create(
            book=self.book_old,
            slug="artikel-3",
            section="Art. 3",
            title="Article Three",
            order=3,
            previous=self.law2_old,
        )

        # Create laws in new revision (artikel-2 was removed)
        self.law1_new = Law.objects.create(
            book=self.book_new,
            slug="artikel-1",
            section="Art. 1",
            title="Article One (Updated)",
            order=1,
        )
        self.law3_new = Law.objects.create(
            book=self.book_new,
            slug="artikel-3",
            section="Art. 3",
            title="Article Three (Updated)",
            order=3,
            previous=self.law1_new,
        )

    def test_get_next_returns_none_for_last_law(self):
        """Test that get_next() returns None for the last law in a book."""
        next_law = self.law3_old.get_next()
        self.assertIsNone(next_law)

    def test_get_next_returns_correct_law(self):
        """Test that get_next() returns the correct next law."""
        next_law = self.law1_old.get_next()
        self.assertEqual(next_law, self.law2_old)

    def test_has_next_true_when_next_exists(self):
        """Test that has_next() returns True when next law exists."""
        self.assertTrue(self.law1_old.has_next())
        self.assertTrue(self.law2_old.has_next())

    def test_has_next_false_when_no_next(self):
        """Test that has_next() returns False for last law."""
        self.assertFalse(self.law3_old.has_next())

    def test_get_latest_revision_url_when_law_exists(self):
        """Test get_latest_revision_url when law exists in latest revision."""
        url = self.law1_old.get_latest_revision_url()
        expected_url = self.law1_new.get_absolute_url()
        self.assertEqual(url, expected_url)

    def test_get_latest_revision_url_when_law_not_exists(self):
        """Test get_latest_revision_url when law doesn't exist in latest."""
        # law2_old doesn't exist in new revision
        url = self.law2_old.get_latest_revision_url()
        # Should return the book URL instead
        expected_url = self.book_new.get_absolute_url()
        self.assertEqual(url, expected_url)


class SetLawBookRevisionCommandTest(TransactionTestCase):
    """Test the set_law_book_revision management command."""

    def setUp(self):
        """Create test lawbooks with various revision states."""
        # Create books with incorrect latest flags
        LawBook.objects.create(
            code="GB1",
            title="Gesetzbuch 1",
            slug="gb1",
            revision_date=datetime.date(2010, 1, 1),
            latest=True,  # Should be False
        )
        LawBook.objects.create(
            code="GB1",
            title="Gesetzbuch 1",
            slug="gb1",
            revision_date=datetime.date(2020, 1, 1),
            latest=False,  # Should be True
        )
        LawBook.objects.create(
            code="GB2",
            title="Gesetzbuch 2",
            slug="gb2",
            revision_date=datetime.date(2015, 6, 1),
            latest=True,  # Correct
        )

    def test_command_sets_correct_latest_flags(self):
        """Test that command correctly sets latest=True for newest revisions."""
        # Run the command
        call_command("set_law_book_revision")

        # Check GB1 - newest should be latest
        gb1_old = LawBook.objects.get(code="GB1", revision_date=datetime.date(2010, 1, 1))
        gb1_new = LawBook.objects.get(code="GB1", revision_date=datetime.date(2020, 1, 1))
        self.assertFalse(gb1_old.latest)
        self.assertTrue(gb1_new.latest)

        # Check GB2 - should remain latest
        gb2 = LawBook.objects.get(code="GB2")
        self.assertTrue(gb2.latest)

    def test_command_no_race_condition(self):
        """Test that command maintains at least one latest=True at all times."""
        # This is hard to test directly, but we verify the end state
        call_command("set_law_book_revision")

        # Verify each code has exactly one latest=True
        for code in ["GB1", "GB2"]:
            latest_count = LawBook.objects.filter(code=code, latest=True).count()
            self.assertEqual(
                latest_count,
                1,
                f"Code {code} should have exactly one latest=True",
            )

    def test_command_with_multiple_codes(self):
        """Test command with multiple lawbook codes."""
        # Add more books
        LawBook.objects.create(
            code="GB3",
            title="Gesetzbuch 3",
            slug="gb3",
            revision_date=datetime.date(2018, 3, 1),
            latest=False,
        )
        LawBook.objects.create(
            code="GB3",
            title="Gesetzbuch 3",
            slug="gb3",
            revision_date=datetime.date(2019, 9, 1),
            latest=False,
        )

        call_command("set_law_book_revision")

        # Verify latest is set for all codes
        for code in ["GB1", "GB2", "GB3"]:
            latest_books = LawBook.objects.filter(code=code, latest=True)
            self.assertEqual(latest_books.count(), 1)


class LawBookRevisionViewTest(TestCase):
    """Test views with revision support."""

    fixtures = ["laws/laws.json"]

    @skipUnless(settings.TEST_WITH_ES, "Elasticsearch not available")
    def test_book_view_with_revision_date(self):
        """Test viewing a specific revision via query parameter."""
        res = self.client.get(
            reverse("laws:book", args=("gg",)) + "?revision_date=2010-07-26"
        )
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "Grundgesetz")
        # Should show the specific revision date
        self.assertContains(res, "2010-07-26")

    @skipUnless(settings.TEST_WITH_ES, "Elasticsearch not available")
    def test_book_view_without_revision_date_shows_latest(self):
        """Test that viewing without revision_date shows latest."""
        res = self.client.get(reverse("laws:book", args=("gg",)))
        self.assertEqual(res.status_code, 200)
        # Should show the latest revision (2012-07-16 per fixture)
        self.assertContains(res, "2012-07-16")

    @skipUnless(settings.TEST_WITH_ES, "Elasticsearch not available")
    def test_book_view_with_invalid_revision_date(self):
        """Test viewing with non-existent revision_date."""
        res = self.client.get(
            reverse("laws:book", args=("gg",)) + "?revision_date=1999-01-01"
        )
        # Should show latest and display warning
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "Grundgesetz")

    @skipUnless(settings.TEST_WITH_ES, "Elasticsearch not available")
    def test_law_view_shows_outdated_warning(self):
        """Test that viewing old revision shows outdated warning."""
        # Get a law from the old revision
        old_book = LawBook.objects.get(slug="gg", revision_date="2010-07-26")
        law = Law.objects.filter(book=old_book).first()
        if law:
            res = self.client.get(
                reverse("laws:law", args=("gg", law.slug))
                + "?revision_date=2010-07-26"
            )
            self.assertEqual(res.status_code, 200)
            self.assertContains(res, "outdated revision")

    @skipUnless(settings.TEST_WITH_ES, "Elasticsearch not available")
    def test_law_view_latest_no_warning(self):
        """Test that viewing latest revision doesn't show warning."""
        latest_book = LawBook.objects.get(slug="gg", latest=True)
        law = Law.objects.filter(book=latest_book).first()
        if law:
            res = self.client.get(reverse("laws:law", args=("gg", law.slug)))
            self.assertEqual(res.status_code, 200)
            self.assertNotContains(res, "outdated revision")


class LawNavigationTest(TestCase):
    """Test law navigation (previous/next)."""

    def setUp(self):
        """Create a chain of laws."""
        self.book = LawBook.objects.create(
            code="NavGB",
            title="Navigation Test",
            slug="navgb",
            latest=True,
        )
        self.law1 = Law.objects.create(
            book=self.book,
            slug="section-1",
            section="§ 1",
            title="First Law",
            order=1,
        )
        self.law2 = Law.objects.create(
            book=self.book,
            slug="section-2",
            section="§ 2",
            title="Second Law",
            order=2,
            previous=self.law1,
        )
        self.law3 = Law.objects.create(
            book=self.book,
            slug="section-3",
            section="§ 3",
            title="Third Law",
            order=3,
            previous=self.law2,
        )

    def test_law_chain_navigation(self):
        """Test navigating through law chain."""
        # Test forward navigation
        self.assertEqual(self.law1.get_next(), self.law2)
        self.assertEqual(self.law2.get_next(), self.law3)
        self.assertIsNone(self.law3.get_next())

        # Test backward navigation
        self.assertIsNone(self.law1.get_previous())
        self.assertEqual(self.law2.get_previous(), self.law1)
        self.assertEqual(self.law3.get_previous(), self.law2)

    def test_has_next_and_previous(self):
        """Test has_next and has_previous methods."""
        self.assertTrue(self.law1.has_next())
        self.assertFalse(self.law1.has_previous())

        self.assertTrue(self.law2.has_next())
        self.assertTrue(self.law2.has_previous())

        self.assertFalse(self.law3.has_next())
        self.assertTrue(self.law3.has_previous())


