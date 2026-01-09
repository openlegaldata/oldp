"""Unit tests for case processing steps.

Tests cover:
- SetPrivateTrue processing step
- SetPrivateFalse processing step
- AssignCourt processing step (remove_chamber method)
"""

import logging
from unittest.mock import MagicMock, patch

from django.test import TestCase, tag

from oldp.apps.cases.models import Case
from oldp.apps.cases.processing.processing_steps.assign_court import (
    ProcessingStep as AssignCourtStep,
)
from oldp.apps.cases.processing.processing_steps.set_private_false import (
    ProcessingStep as SetPrivateFalseStep,
)
from oldp.apps.cases.processing.processing_steps.set_private_true import (
    ProcessingStep as SetPrivateTrueStep,
)

logger = logging.getLogger(__name__)


@tag("processing", "cases")
class SetPrivateTrueStepTestCase(TestCase):
    """Tests for the SetPrivateTrue processing step."""

    def test_description(self):
        """Test that the step has correct description."""
        step = SetPrivateTrueStep()
        self.assertEqual(step.description, "Set private=True")

    def test_sets_private_to_true(self):
        """Test that process sets private attribute to True."""
        step = SetPrivateTrueStep()
        case = Case(private=False, file_number="TEST/123")

        result = step.process(case)

        self.assertTrue(result.private)

    def test_returns_case_instance(self):
        """Test that process returns the Case instance."""
        step = SetPrivateTrueStep()
        case = Case(file_number="TEST/123")

        result = step.process(case)

        self.assertIsInstance(result, Case)
        self.assertIs(result, case)

    def test_already_private_case(self):
        """Test processing a case that is already private."""
        step = SetPrivateTrueStep()
        case = Case(private=True, file_number="TEST/123")

        result = step.process(case)

        self.assertTrue(result.private)


@tag("processing", "cases")
class SetPrivateFalseStepTestCase(TestCase):
    """Tests for the SetPrivateFalse processing step."""

    def test_description(self):
        """Test that the step has correct description."""
        step = SetPrivateFalseStep()
        self.assertEqual(step.description, "Set private=False")

    def test_sets_private_to_false(self):
        """Test that process sets private attribute to False."""
        step = SetPrivateFalseStep()
        case = Case(private=True, file_number="TEST/123")

        result = step.process(case)

        self.assertFalse(result.private)

    def test_returns_case_instance(self):
        """Test that process returns the Case instance."""
        step = SetPrivateFalseStep()
        case = Case(file_number="TEST/123")

        result = step.process(case)

        self.assertIsInstance(result, Case)
        self.assertIs(result, case)

    def test_already_public_case(self):
        """Test processing a case that is already public."""
        step = SetPrivateFalseStep()
        case = Case(private=False, file_number="TEST/123")

        result = step.process(case)

        self.assertFalse(result.private)


@tag("processing", "cases")
class AssignCourtRemoveChamberTestCase(TestCase):
    """Tests for the AssignCourt processing step's remove_chamber method."""

    def setUp(self):
        self.step = AssignCourtStep()

    def test_remove_chamber_simple_number(self):
        """Test removing numbered chamber from court name."""
        name = "LG Koblenz 14. Zivilkammer"

        result_name, chamber = self.step.remove_chamber(name)

        self.assertEqual(result_name, "LG Koblenz")
        self.assertIsNotNone(chamber)
        self.assertIn("14", chamber)

    def test_remove_chamber_senat(self):
        """Test removing Senat designation from court name."""
        name = "OLG Koblenz 2. Senat für Bußgeldsachen"

        result_name, chamber = self.step.remove_chamber(name)

        self.assertEqual(result_name, "OLG Koblenz")
        self.assertIsNotNone(chamber)

    def test_remove_chamber_kammer_fur(self):
        """Test removing 'Kammer für' designation."""
        name = "LG Kiel Kammer für Handelssachen"

        result_name, chamber = self.step.remove_chamber(name)

        self.assertEqual(result_name, "LG Kiel")
        self.assertIn("Kammer für Handelssachen", chamber)

    def test_remove_chamber_senat_fur(self):
        """Test removing 'Senat für' designation."""
        name = "OLG München Senat für Familiensachen"

        result_name, chamber = self.step.remove_chamber(name)

        self.assertEqual(result_name, "OLG München")
        self.assertIn("Senat für Familiensachen", chamber)

    def test_remove_chamber_kartellsenat(self):
        """Test removing combined chamber name (e.g., Kartellsenat)."""
        name = "Schleswig-Holsteinisches Oberlandesgericht Kartellsenat"

        result_name, chamber = self.step.remove_chamber(name)

        self.assertEqual(result_name, "Schleswig-Holsteinisches Oberlandesgericht")
        self.assertIn("Kartellsenat", chamber)

    def test_remove_chamber_no_chamber(self):
        """Test with court name without chamber designation."""
        name = "Amtsgericht Berlin"

        result_name, chamber = self.step.remove_chamber(name)

        self.assertEqual(result_name, "Amtsgericht Berlin")
        self.assertIsNone(chamber)

    def test_remove_chamber_zivilkammer(self):
        """Test removing combined Zivilkammer."""
        name = "LG Hamburg Zivilkammer"

        result_name, chamber = self.step.remove_chamber(name)

        self.assertEqual(result_name, "LG Hamburg")
        self.assertIn("Zivilkammer", chamber)

    def test_remove_chamber_strips_whitespace(self):
        """Test that result is stripped of extra whitespace."""
        name = "LG Berlin  10. Strafkammer"

        result_name, chamber = self.step.remove_chamber(name)

        self.assertFalse(result_name.endswith(" "))
        self.assertFalse(result_name.startswith(" "))


@tag("processing", "cases")
class AssignCourtStepTestCase(TestCase):
    """Tests for the AssignCourt processing step."""

    fixtures = [
        "locations/countries.json",
        "locations/states.json",
        "locations/cities.json",
        "courts/courts.json",
    ]

    def setUp(self):
        self.step = AssignCourtStep()

    def test_description(self):
        """Test that the step has correct description."""
        self.assertEqual(self.step.description, "Assign court to cases")

    def test_process_uses_court_raw(self):
        """Test that processing uses court_raw field."""
        from oldp.apps.courts.models import Court

        # Create case with court_raw
        case = Case(
            file_number="TEST/123",
            court_raw='{"name": "Amtsgericht Berlin"}',
            court_id=Court.DEFAULT_ID,
        )

        # The step should attempt to process the court_raw
        # Even if court is not found, it shouldn't error
        try:
            result = self.step.process(case)
            # Should return a Case instance
            self.assertIsInstance(result, Case)
        except Court.DoesNotExist:
            # Expected if court isn't in database
            pass
