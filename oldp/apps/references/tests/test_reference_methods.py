"""Unit tests for Reference and ReferenceMarker model methods.

Tests cover:
- Reference.get_target()
- Reference.has_law_target() / has_case_target()
- Reference.get_title()
- Reference.is_assigned()
- Reference.set_to_hash()
- ReferenceMarker.remove_markers()
- ReferenceMarker.make_markers_clickable()
"""

import hashlib
import logging

from django.test import TestCase, tag

from oldp.apps.cases.models import Case
from oldp.apps.laws.models import Law, LawBook
from oldp.apps.references.models import (
    Reference,
    ReferenceMarker,
)

logger = logging.getLogger(__name__)


@tag("models", "references")
class ReferenceGetTargetTestCase(TestCase):
    """Tests for Reference.get_target() method."""

    fixtures = [
        "locations/countries.json",
        "locations/states.json",
        "locations/cities.json",
        "courts/courts.json",
        "cases/cases.json",
    ]

    def test_get_target_with_law(self):
        """Test get_target returns law when law is set."""
        law_book = LawBook.objects.create(title="Test Book", slug="test-book")
        law = Law.objects.create(
            book=law_book, title="Test Law", slug="test-law", section="1"
        )
        ref = Reference(law=law, to="test")

        self.assertEqual(ref.get_target(), law)

    def test_get_target_with_case(self):
        """Test get_target returns case when case is set."""
        case = Case.objects.get(pk=1)
        ref = Reference(case=case, to="test")

        self.assertEqual(ref.get_target(), case)

    def test_get_target_with_neither(self):
        """Test get_target returns None when neither law nor case is set."""
        ref = Reference(to="unassigned")

        self.assertIsNone(ref.get_target())

    def test_get_target_prefers_law_over_case(self):
        """Test get_target returns law when both are set."""
        law_book = LawBook.objects.create(title="Test Book", slug="test-book")
        law = Law.objects.create(
            book=law_book, title="Test Law", slug="test-law", section="1"
        )
        case = Case.objects.get(pk=1)
        ref = Reference(law=law, case=case, to="test")

        self.assertEqual(ref.get_target(), law)


@tag("models", "references")
class ReferenceHasTargetTestCase(TestCase):
    """Tests for Reference.has_law_target() and has_case_target() methods."""

    fixtures = [
        "locations/countries.json",
        "locations/states.json",
        "locations/cities.json",
        "courts/courts.json",
        "cases/cases.json",
    ]

    def test_has_law_target_true(self):
        """Test has_law_target returns True when law is set."""
        law_book = LawBook.objects.create(title="Test Book", slug="test-book")
        law = Law.objects.create(
            book=law_book, title="Test Law", slug="test-law", section="1"
        )
        ref = Reference(law=law, to="test")

        self.assertTrue(ref.has_law_target())

    def test_has_law_target_false(self):
        """Test has_law_target returns False when law is not set."""
        ref = Reference(to="test")

        self.assertFalse(ref.has_law_target())

    def test_has_case_target_true(self):
        """Test has_case_target returns True when case is set."""
        case = Case.objects.get(pk=1)
        ref = Reference(case=case, to="test")

        self.assertTrue(ref.has_case_target())

    def test_has_case_target_false(self):
        """Test has_case_target returns False when case is not set."""
        ref = Reference(to="test")

        self.assertFalse(ref.has_case_target())


@tag("models", "references")
class ReferenceGetTitleTestCase(TestCase):
    """Tests for Reference.get_title() method."""

    fixtures = [
        "locations/countries.json",
        "locations/states.json",
        "locations/cities.json",
        "courts/courts.json",
        "cases/cases.json",
    ]

    def test_get_title_with_law(self):
        """Test get_title returns law title when law is set."""
        law_book = LawBook.objects.create(title="Test Book", slug="test-book")
        law = Law.objects.create(
            book=law_book, title="Test Law Title", slug="test-law", section="1"
        )
        ref = Reference(law=law, to="test")

        self.assertEqual(ref.get_title(), law.get_title())

    def test_get_title_with_case(self):
        """Test get_title returns case title when case is set."""
        case = Case.objects.get(pk=1)
        ref = Reference(case=case, to="test")

        self.assertEqual(ref.get_title(), case.get_title())

    def test_get_title_with_unassigned(self):
        """Test get_title returns 'to' field when neither target is set."""
        ref = Reference(to="§ 123 BGB")

        self.assertEqual(ref.get_title(), "§ 123 BGB")


@tag("models", "references")
class ReferenceIsAssignedTestCase(TestCase):
    """Tests for Reference.is_assigned() method."""

    fixtures = [
        "locations/countries.json",
        "locations/states.json",
        "locations/cities.json",
        "courts/courts.json",
        "cases/cases.json",
    ]

    def test_is_assigned_with_law(self):
        """Test is_assigned returns True when law is set."""
        law_book = LawBook.objects.create(title="Test Book", slug="test-book")
        law = Law.objects.create(
            book=law_book, title="Test Law", slug="test-law", section="1"
        )
        ref = Reference(law=law, to="test")

        self.assertTrue(ref.is_assigned())

    def test_is_assigned_with_case(self):
        """Test is_assigned returns True when case is set."""
        case = Case.objects.get(pk=1)
        ref = Reference(case=case, to="test")

        self.assertTrue(ref.is_assigned())

    def test_is_assigned_with_neither(self):
        """Test is_assigned returns False when neither is set."""
        ref = Reference(to="unassigned")

        self.assertFalse(ref.is_assigned())


@tag("models", "references")
class ReferenceSetToHashTestCase(TestCase):
    """Tests for Reference.set_to_hash() method."""

    fixtures = [
        "locations/countries.json",
        "locations/states.json",
        "locations/cities.json",
        "courts/courts.json",
        "cases/cases.json",
    ]

    def test_set_to_hash_with_law(self):
        """Test set_to_hash generates hash for law reference."""
        law_book = LawBook.objects.create(title="Test Book", slug="test-book")
        law = Law.objects.create(
            book=law_book, title="Test Law", slug="test-law", section="1"
        )
        ref = Reference(law=law, to="test")
        ref.save()

        ref.set_to_hash()

        expected_hash = hashlib.md5(f"law/{law.id}".encode("utf-8")).hexdigest()
        self.assertEqual(ref.to_hash, expected_hash)

    def test_set_to_hash_with_case(self):
        """Test set_to_hash generates hash for case reference."""
        case = Case.objects.get(pk=1)
        ref = Reference(case=case, to="test")

        ref.set_to_hash()

        expected_hash = hashlib.md5(f"case/{case.id}".encode("utf-8")).hexdigest()
        self.assertEqual(ref.to_hash, expected_hash)

    def test_set_to_hash_with_unassigned(self):
        """Test set_to_hash generates hash for unassigned reference."""
        ref = Reference(to="§ 123 BGB")

        ref.set_to_hash()

        expected_hash = hashlib.md5("unassigend/§ 123 BGB".encode("utf-8")).hexdigest()
        self.assertEqual(ref.to_hash, expected_hash)

    def test_set_to_hash_different_refs_different_hashes(self):
        """Test that different references produce different hashes."""
        ref1 = Reference(to="ref1")
        ref2 = Reference(to="ref2")

        ref1.set_to_hash()
        ref2.set_to_hash()

        self.assertNotEqual(ref1.to_hash, ref2.to_hash)


@tag("models", "references")
class ReferenceMarkerRemoveMarkersTestCase(TestCase):
    """Tests for ReferenceMarker.remove_markers() static method."""

    def test_remove_single_marker(self):
        """Test removing a single marker."""
        value = "See [ref=abc123]§ 123 BGB[/ref] for details."

        result = ReferenceMarker.remove_markers(value)

        self.assertEqual(result, "See § 123 BGB for details.")

    def test_remove_multiple_markers(self):
        """Test removing multiple markers."""
        value = "[ref=1]First[/ref] and [ref=2]Second[/ref]"

        result = ReferenceMarker.remove_markers(value)

        self.assertEqual(result, "First and Second")

    def test_remove_nested_text(self):
        """Test that marker text content is preserved."""
        value = "The [ref=uuid-1234]important text[/ref] here."

        result = ReferenceMarker.remove_markers(value)

        self.assertEqual(result, "The important text here.")

    def test_no_markers_unchanged(self):
        """Test that text without markers is unchanged."""
        value = "No markers here."

        result = ReferenceMarker.remove_markers(value)

        self.assertEqual(result, value)

    def test_empty_string(self):
        """Test with empty string."""
        result = ReferenceMarker.remove_markers("")

        self.assertEqual(result, "")

    def test_uuid_style_marker_id(self):
        """Test with UUID-style marker IDs."""
        value = "[ref=550e8400-e29b-41d4-a716-446655440000]Content[/ref]"

        result = ReferenceMarker.remove_markers(value)

        self.assertEqual(result, "Content")


@tag("models", "references")
class ReferenceMarkerMakeClickableTestCase(TestCase):
    """Tests for ReferenceMarker.make_markers_clickable() static method."""

    def test_make_single_marker_clickable(self):
        """Test converting a single marker to clickable link."""
        value = "See [ref=abc123]§ 123 BGB[/ref] for details."

        result = ReferenceMarker.make_markers_clickable(value)

        self.assertIn('href="#refs"', result)
        self.assertIn("onclick=", result)
        self.assertIn('data-marker-id="abc123"', result)
        self.assertIn('class="ref"', result)
        self.assertIn("§ 123 BGB", result)
        self.assertNotIn("[ref=", result)
        self.assertNotIn("[/ref]", result)

    def test_make_multiple_markers_clickable(self):
        """Test converting multiple markers to clickable links."""
        value = "[ref=1]First[/ref] and [ref=2]Second[/ref]"

        result = ReferenceMarker.make_markers_clickable(value)

        self.assertIn('data-marker-id="1"', result)
        self.assertIn('data-marker-id="2"', result)
        self.assertEqual(result.count('class="ref"'), 2)

    def test_no_markers_unchanged(self):
        """Test that text without markers is unchanged."""
        value = "No markers here."

        result = ReferenceMarker.make_markers_clickable(value)

        self.assertEqual(result, value)

    def test_preserves_surrounding_text(self):
        """Test that surrounding text is preserved."""
        value = "Before [ref=x]middle[/ref] after."

        result = ReferenceMarker.make_markers_clickable(value)

        self.assertTrue(result.startswith("Before "))
        self.assertTrue(result.endswith(" after."))
        self.assertIn("middle", result)

    def test_empty_string(self):
        """Test with empty string."""
        result = ReferenceMarker.make_markers_clickable("")

        self.assertEqual(result, "")


@tag("models", "references")
class ReferenceStrRepresentationTestCase(TestCase):
    """Tests for Reference string representations."""

    fixtures = [
        "locations/countries.json",
        "locations/states.json",
        "locations/cities.json",
        "courts/courts.json",
        "cases/cases.json",
    ]

    def test_str_without_count(self):
        """Test __str__ without count attribute."""
        ref = Reference(to="§ 123 BGB")

        result = str(ref)

        self.assertIn("Reference", result)
        self.assertIn("§ 123 BGB", result)

    def test_str_with_count(self):
        """Test __str__ with count attribute."""
        ref = Reference(to="§ 123 BGB")
        ref.count = 5
        ref.to_hash = "abcd1234"

        result = str(ref)

        self.assertIn("count=5", result)
        self.assertIn("abcd1234", result)

    def test_repr_equals_str(self):
        """Test that __repr__ equals __str__."""
        ref = Reference(to="test")

        self.assertEqual(repr(ref), str(ref))
