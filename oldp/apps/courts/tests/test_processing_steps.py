"""Unit tests for court processing steps.

Tests cover:
- AssignJurisdiction processing step
- SetAliases processing step
"""

import logging
from unittest.mock import MagicMock, patch

from django.conf import settings
from django.test import TestCase, override_settings, tag

from oldp.apps.courts.models import Court
from oldp.apps.courts.processing.processing_steps.assign_jurisdiction import (
    ProcessingStep as AssignJurisdictionStep,
)
from oldp.apps.courts.processing.processing_steps.set_aliases import (
    ProcessingStep as SetAliasesStep,
)

logger = logging.getLogger(__name__)


# Mock COURT_JURISDICTIONS and COURT_LEVELS_OF_APPEAL for testing
MOCK_COURT_JURISDICTIONS = {
    "civil": r"(Amtsgericht|Landgericht|Oberlandesgericht)",
    "administrative": r"(Verwaltungsgericht|Oberverwaltungsgericht)",
    "labor": r"(Arbeitsgericht|Landesarbeitsgericht)",
}

MOCK_COURT_LEVELS_OF_APPEAL = {
    "first": r"(Amtsgericht|Arbeitsgericht|Verwaltungsgericht)",
    "second": r"(Landgericht|Landesarbeitsgericht|Oberverwaltungsgericht)",
    "third": r"(Oberlandesgericht|Bundesarbeitsgericht)",
}


@tag("processing", "courts")
class AssignJurisdictionStepTestCase(TestCase):
    """Tests for the AssignJurisdiction processing step."""

    def setUp(self):
        self.step = AssignJurisdictionStep()

    def test_description(self):
        """Test that the step has correct description."""
        self.assertEqual(self.step.description, "Assign jurisdiction")

    @override_settings(
        COURT_JURISDICTIONS=MOCK_COURT_JURISDICTIONS,
        COURT_LEVELS_OF_APPEAL=MOCK_COURT_LEVELS_OF_APPEAL,
    )
    def test_assigns_civil_jurisdiction(self):
        """Test assigning civil jurisdiction based on court name."""
        court = Court(name="Landgericht Berlin")

        result = self.step.process(court)

        self.assertEqual(result.jurisdiction, "civil")

    @override_settings(
        COURT_JURISDICTIONS=MOCK_COURT_JURISDICTIONS,
        COURT_LEVELS_OF_APPEAL=MOCK_COURT_LEVELS_OF_APPEAL,
    )
    def test_assigns_administrative_jurisdiction(self):
        """Test assigning administrative jurisdiction."""
        court = Court(name="Verwaltungsgericht Hamburg")

        result = self.step.process(court)

        self.assertEqual(result.jurisdiction, "administrative")

    @override_settings(
        COURT_JURISDICTIONS=MOCK_COURT_JURISDICTIONS,
        COURT_LEVELS_OF_APPEAL=MOCK_COURT_LEVELS_OF_APPEAL,
    )
    def test_assigns_labor_jurisdiction(self):
        """Test assigning labor jurisdiction."""
        court = Court(name="Arbeitsgericht München")

        result = self.step.process(court)

        self.assertEqual(result.jurisdiction, "labor")

    @override_settings(
        COURT_JURISDICTIONS=MOCK_COURT_JURISDICTIONS,
        COURT_LEVELS_OF_APPEAL=MOCK_COURT_LEVELS_OF_APPEAL,
    )
    def test_assigns_first_level_of_appeal(self):
        """Test assigning first level of appeal."""
        court = Court(name="Amtsgericht Köln")

        result = self.step.process(court)

        self.assertEqual(result.level_of_appeal, "first")

    @override_settings(
        COURT_JURISDICTIONS=MOCK_COURT_JURISDICTIONS,
        COURT_LEVELS_OF_APPEAL=MOCK_COURT_LEVELS_OF_APPEAL,
    )
    def test_assigns_second_level_of_appeal(self):
        """Test assigning second level of appeal."""
        court = Court(name="Landgericht Frankfurt")

        result = self.step.process(court)

        self.assertEqual(result.level_of_appeal, "second")

    @override_settings(
        COURT_JURISDICTIONS=MOCK_COURT_JURISDICTIONS,
        COURT_LEVELS_OF_APPEAL=MOCK_COURT_LEVELS_OF_APPEAL,
    )
    def test_assigns_third_level_of_appeal(self):
        """Test assigning third level of appeal."""
        court = Court(name="Oberlandesgericht Düsseldorf")

        result = self.step.process(court)

        self.assertEqual(result.level_of_appeal, "third")

    @override_settings(COURT_JURISDICTIONS={}, COURT_LEVELS_OF_APPEAL={})
    def test_no_match_leaves_empty(self):
        """Test that no match leaves jurisdiction/level empty."""
        court = Court(name="Unknown Court")

        result = self.step.process(court)

        # Should not have jurisdiction set if no pattern matches
        self.assertIsNone(result.jurisdiction)
        self.assertIsNone(result.level_of_appeal)

    @override_settings(
        COURT_JURISDICTIONS=MOCK_COURT_JURISDICTIONS,
        COURT_LEVELS_OF_APPEAL=MOCK_COURT_LEVELS_OF_APPEAL,
    )
    def test_case_insensitive_match(self):
        """Test that matching is case insensitive."""
        court = Court(name="LANDGERICHT BERLIN")

        result = self.step.process(court)

        self.assertEqual(result.jurisdiction, "civil")

    @override_settings(
        COURT_JURISDICTIONS=MOCK_COURT_JURISDICTIONS,
        COURT_LEVELS_OF_APPEAL=MOCK_COURT_LEVELS_OF_APPEAL,
    )
    def test_returns_court_instance(self):
        """Test that process returns the Court instance."""
        court = Court(name="Amtsgericht Berlin")

        result = self.step.process(court)

        self.assertIsInstance(result, Court)
        self.assertIs(result, court)


@tag("processing", "courts")
class SetAliasesStepTestCase(TestCase):
    """Tests for the SetAliases processing step."""

    fixtures = [
        "locations/countries.json",
        "locations/states.json",
        "locations/cities.json",
        "courts/courts.json",
    ]

    def setUp(self):
        self.step = SetAliasesStep()

    def test_description(self):
        """Test that the step has correct description."""
        self.assertEqual(self.step.description, "Set aliases for courts")

    def test_combine_type_location_generates_both_orders(self):
        """Test that combine_type_location generates both orderings."""
        types = ["AG", "Amtsgericht"]
        location = "Berlin"

        results = list(self.step.combine_type_location(types, location))

        self.assertIn("AG Berlin", results)
        self.assertIn("Berlin AG", results)
        self.assertIn("Amtsgericht Berlin", results)
        self.assertIn("Berlin Amtsgericht", results)
        self.assertEqual(len(results), 4)

    def test_process_includes_court_name_as_alias(self):
        """Test that court name is always included as alias."""
        court = MagicMock(spec=Court)
        court.name = "Test Court"
        court.court_type = "AG"

        # Mock settings to return empty levels
        with patch.object(settings, "COURT_TYPES") as mock_types:
            mock_types.get_type.return_value = {"levels": [], "name": "Amtsgericht"}

            result = self.step.process(court)

            self.assertIn("Test Court", result.aliases)

    def test_process_handles_no_court_type(self):
        """Test processing court without court_type."""
        court = MagicMock(spec=Court)
        court.name = "Unknown Court"
        court.court_type = None

        result = self.step.process(court)

        # Should return early without setting aliases
        self.assertIs(result, court)

    def test_process_returns_court_instance(self):
        """Test that process returns the Court instance."""
        court = MagicMock(spec=Court)
        court.name = "Test Court"
        court.court_type = None

        result = self.step.process(court)

        self.assertIs(result, court)


@tag("processing", "courts")
class SetAliasesCombineTypeLocationTestCase(TestCase):
    """Detailed tests for the combine_type_location method."""

    def setUp(self):
        self.step = SetAliasesStep()

    def test_single_type_single_location(self):
        """Test with single type and location."""
        results = list(self.step.combine_type_location(["VG"], "Hamburg"))

        self.assertEqual(results, ["VG Hamburg", "Hamburg VG"])

    def test_multiple_types(self):
        """Test with multiple types."""
        results = list(
            self.step.combine_type_location(["VG", "Verwaltungsgericht"], "Hamburg")
        )

        self.assertEqual(len(results), 4)
        self.assertIn("VG Hamburg", results)
        self.assertIn("Hamburg VG", results)
        self.assertIn("Verwaltungsgericht Hamburg", results)
        self.assertIn("Hamburg Verwaltungsgericht", results)

    def test_empty_types(self):
        """Test with empty types list."""
        results = list(self.step.combine_type_location([], "Hamburg"))

        self.assertEqual(results, [])

    def test_location_with_spaces(self):
        """Test with location containing spaces."""
        results = list(self.step.combine_type_location(["AG"], "Frankfurt am Main"))

        self.assertIn("AG Frankfurt am Main", results)
        self.assertIn("Frankfurt am Main AG", results)

    def test_location_with_special_characters(self):
        """Test with location containing special characters."""
        results = list(self.step.combine_type_location(["AG"], "Frankfurt (Oder)"))

        self.assertIn("AG Frankfurt (Oder)", results)
        self.assertIn("Frankfurt (Oder) AG", results)
