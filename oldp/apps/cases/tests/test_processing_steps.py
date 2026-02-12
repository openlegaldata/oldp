"""Unit tests for case processing steps.

Tests cover:
- SetReviewPending processing step
- SetReviewAccepted processing step
- AssignCourt processing step (remove_chamber method)
"""

import logging

from django.test import TestCase, tag

from oldp.apps.cases.models import Case
from oldp.apps.cases.processing.processing_steps.assign_court import (
    ProcessingStep as AssignCourtStep,
)
from oldp.apps.cases.processing.processing_steps.set_review_accepted import (
    ProcessingStep as SetReviewAcceptedStep,
)
from oldp.apps.cases.processing.processing_steps.set_review_pending import (
    ProcessingStep as SetReviewPendingStep,
)

logger = logging.getLogger(__name__)


@tag("processing", "cases")
class SetReviewPendingStepTestCase(TestCase):
    """Tests for the SetReviewPending processing step."""

    def test_description(self):
        """Test that the step has correct description."""
        step = SetReviewPendingStep()
        self.assertEqual(step.description, "Set review_status=pending")

    def test_sets_review_status_to_pending(self):
        """Test that process sets review_status to pending."""
        step = SetReviewPendingStep()
        case = Case(review_status="accepted", file_number="TEST/123")

        result = step.process(case)

        self.assertEqual(result.review_status, "pending")

    def test_returns_case_instance(self):
        """Test that process returns the Case instance."""
        step = SetReviewPendingStep()
        case = Case(file_number="TEST/123")

        result = step.process(case)

        self.assertIsInstance(result, Case)
        self.assertIs(result, case)

    def test_already_pending_case(self):
        """Test processing a case that is already pending."""
        step = SetReviewPendingStep()
        case = Case(review_status="pending", file_number="TEST/123")

        result = step.process(case)

        self.assertEqual(result.review_status, "pending")


@tag("processing", "cases")
class SetReviewAcceptedStepTestCase(TestCase):
    """Tests for the SetReviewAccepted processing step."""

    def test_description(self):
        """Test that the step has correct description."""
        step = SetReviewAcceptedStep()
        self.assertEqual(step.description, "Set review_status=accepted")

    def test_sets_review_status_to_accepted(self):
        """Test that process sets review_status to accepted."""
        step = SetReviewAcceptedStep()
        case = Case(review_status="pending", file_number="TEST/123")

        result = step.process(case)

        self.assertEqual(result.review_status, "accepted")

    def test_returns_case_instance(self):
        """Test that process returns the Case instance."""
        step = SetReviewAcceptedStep()
        case = Case(file_number="TEST/123")

        result = step.process(case)

        self.assertIsInstance(result, Case)
        self.assertIs(result, case)

    def test_already_accepted_case(self):
        """Test processing a case that is already accepted."""
        step = SetReviewAcceptedStep()
        case = Case(review_status="accepted", file_number="TEST/123")

        result = step.process(case)

        self.assertEqual(result.review_status, "accepted")


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
