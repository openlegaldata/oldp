"""Unit tests for the filters module.

Tests cover:
- LazyOrderingFilter build_choices method
"""

import logging

from django.test import TestCase, tag
from django.utils.translation import gettext_lazy as _

from oldp.apps.lib.filters import LazyOrderingFilter

logger = logging.getLogger(__name__)


@tag("lib", "filters")
class LazyOrderingFilterTestCase(TestCase):
    """Tests for the LazyOrderingFilter class."""

    def test_build_choices_single_field(self):
        """Test build_choices with a single field."""
        filter_instance = LazyOrderingFilter()
        fields = {"name": "name"}
        labels = {}

        choices = filter_instance.build_choices(fields, labels)

        # Should have ascending and descending for each field
        self.assertEqual(len(choices), 2)
        # First should be ascending
        self.assertEqual(choices[0][0], "name")
        # Second should be descending
        self.assertEqual(choices[1][0], "-name")

    def test_build_choices_multiple_fields(self):
        """Test build_choices with multiple fields."""
        filter_instance = LazyOrderingFilter()
        fields = {"name": "name", "date": "date", "title": "title"}
        labels = {}

        choices = filter_instance.build_choices(fields, labels)

        # Should have 2 choices (asc + desc) for each of 3 fields = 6 total
        self.assertEqual(len(choices), 6)

        # Check interleaving pattern: asc, desc, asc, desc, asc, desc
        params = [c[0] for c in choices]
        # Every odd index (1, 3, 5) should start with '-'
        for i, param in enumerate(params):
            if i % 2 == 1:
                self.assertTrue(param.startswith("-"), f"Expected descending at index {i}")
            else:
                self.assertFalse(
                    param.startswith("-"), f"Expected ascending at index {i}"
                )

    def test_build_choices_with_labels(self):
        """Test build_choices with custom labels."""
        filter_instance = LazyOrderingFilter()
        fields = {"name": "name"}
        labels = {"name": _("Name Field")}

        choices = filter_instance.build_choices(fields, labels)

        # Ascending label should use provided label
        self.assertEqual(str(choices[0][1]), "Name Field")
        # Descending label should append "(descending)"
        self.assertIn("descending", str(choices[1][1]))

    def test_build_choices_with_descending_labels(self):
        """Test build_choices with custom descending labels."""
        filter_instance = LazyOrderingFilter()
        fields = {"name": "name"}
        labels = {"name": _("Name"), "-name": _("Name (Z-A)")}

        choices = filter_instance.build_choices(fields, labels)

        # Descending should use custom label if provided
        self.assertEqual(str(choices[1][1]), "Name (Z-A)")

    def test_build_choices_generates_pretty_name(self):
        """Test that build_choices generates pretty names for unlabeled fields."""
        filter_instance = LazyOrderingFilter()
        fields = {"created_at": "created_at"}
        labels = {}

        choices = filter_instance.build_choices(fields, labels)

        # Should generate pretty name from field name (underscores to spaces, capitalized)
        self.assertIn("Created at", str(choices[0][1]))

    def test_build_choices_empty_fields(self):
        """Test build_choices with empty fields."""
        filter_instance = LazyOrderingFilter()
        fields = {}
        labels = {}

        choices = filter_instance.build_choices(fields, labels)

        self.assertEqual(len(choices), 0)

    def test_build_choices_interleaved_order(self):
        """Test that ascending and descending choices are interleaved."""
        filter_instance = LazyOrderingFilter()
        fields = {"a": "a", "b": "b"}
        labels = {}

        choices = filter_instance.build_choices(fields, labels)

        # Pattern should be: a, -a, b, -b (interleaved)
        params = [c[0] for c in choices]

        # Find positions
        a_pos = params.index("a") if "a" in params else -1
        neg_a_pos = params.index("-a") if "-a" in params else -1
        b_pos = params.index("b") if "b" in params else -1
        neg_b_pos = params.index("-b") if "-b" in params else -1

        # Verify interleaving: ascending immediately followed by descending
        self.assertEqual(neg_a_pos, a_pos + 1)
        self.assertEqual(neg_b_pos, b_pos + 1)

    def test_build_choices_preserves_field_order(self):
        """Test that build_choices preserves the order of fields."""
        filter_instance = LazyOrderingFilter()
        # Using ordered dict behavior in Python 3.7+
        fields = {"z_field": "z_field", "a_field": "a_field", "m_field": "m_field"}
        labels = {}

        choices = filter_instance.build_choices(fields, labels)

        # Get ascending params in order
        ascending_params = [c[0] for c in choices if not c[0].startswith("-")]

        # Should preserve dict order (z, a, m), not alphabetical (a, m, z)
        self.assertEqual(ascending_params, ["z_field", "a_field", "m_field"])

    def test_inherits_from_ordering_filter(self):
        """Test that LazyOrderingFilter inherits from OrderingFilter."""
        import django_filters

        filter_instance = LazyOrderingFilter()
        self.assertIsInstance(filter_instance, django_filters.OrderingFilter)
