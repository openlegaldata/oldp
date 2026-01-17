"""
Court resolver service for resolving court from name/string input.

Extracted from assign_court processing step for reuse in API.
"""

import logging
import re
from typing import Optional, Tuple

from django.conf import settings

from oldp.apps.cases.exceptions import CourtNotFoundError
from oldp.apps.courts.apps import CourtLocationLevel
from oldp.apps.courts.models import City, Court, State
from oldp.utils import find_from_mapping

logger = logging.getLogger(__name__)


class CourtResolver:
    """
    Service to resolve court from name/string input.

    This service extracts the court resolution logic from the assign_court
    processing step to allow reuse in the case creation API.
    """

    def remove_chamber(self, name: str) -> Tuple[str, Optional[str]]:
        """
        Extract chamber designation from court name.

        Examples:
            - "LG Kiel Kammer für Handelssachen" -> ("LG Kiel", "Kammer für Handelssachen")
            - "LG Koblenz 14. Zivilkammer" -> ("LG Koblenz", "14. Zivilkammer")
            - "OLG Koblenz 2. Senat für Bußgeldsachen" -> ("OLG Koblenz", "2. Senat für Bußgeldsachen")

        Args:
            name: Court name potentially containing chamber designation

        Returns:
            Tuple of (court_name_without_chamber, chamber_designation or None)
        """
        chamber = None
        patterns = [
            r"\s([0-9]+)(.*)$",
            r"\s(Senat|Kammer) für(.*)$",
            r"\s([a-zA-Z]+)(senat|kammer)(.*)$",
        ]

        for pattern in patterns:
            compiled_pattern = re.compile(pattern)
            match = re.search(compiled_pattern, name)
            if match:
                name = name[: match.start()] + name[match.end() :]
                chamber = match.group(0).strip()

        return name.strip(), chamber

    def find_court(self, court_name: str, court_code: Optional[str] = None) -> Court:
        """
        Find court by name, code, or alias.

        Resolution order:
        1. By code (if provided)
        2. By exact name match (if name has no spaces)
        3. By court type + state location
        4. By court type + city location
        5. By alias (case-insensitive)

        Args:
            court_name: Court name to search for
            court_code: Optional court code (e.g., "EuGH", "BGH")

        Returns:
            Court instance

        Raises:
            CourtNotFoundError: If court cannot be resolved
        """
        # Try to find by code first
        if court_code:
            try:
                return Court.objects.get(code=court_code)
            except Court.DoesNotExist:
                pass

        if not court_name:
            raise CourtNotFoundError("Court name is required")

        # Handle special case for EU court
        if court_name == "EU":
            try:
                return Court.objects.get(code="EuGH")
            except Court.DoesNotExist:
                pass

        # Try exact name match first
        try:
            return Court.objects.get(name=court_name)
        except Court.DoesNotExist:
            pass

        # Determine court type
        court_type = Court.extract_type_code_from_name(court_name)

        if court_type is None:
            # Try alias search as fallback
            court = self._find_by_alias(court_name)
            if court:
                return court
            raise CourtNotFoundError(
                f"Could not determine court type from name: {court_name}"
            )

        try:
            location_levels = settings.COURT_TYPES.get_type(court_type)["levels"]
        except (KeyError, TypeError):
            raise CourtNotFoundError(
                f"Unknown court type: {court_type}"
            )

        # Look for states
        if CourtLocationLevel.STATE in location_levels:
            court = self._find_by_state(court_name, court_type)
            if court:
                return court

        # Look for cities
        if CourtLocationLevel.CITY in location_levels:
            court = self._find_by_city(court_name, court_type)
            if court:
                return court

        # Search by alias as last resort
        court = self._find_by_alias(court_name)
        if court:
            return court

        raise CourtNotFoundError(
            f"Could not resolve court from name: {court_name}"
        )

    def _find_by_state(self, court_name: str, court_type: str) -> Optional[Court]:
        """Find court by state and type."""
        state_id_mapping = {}
        for state_id, state_name in State.objects.values_list("id", "name"):
            if state_name:
                state_id_mapping[state_name] = state_id
                # Add variations, e.g. Hamburg_er, Holstein_isches
                for variation in ["es", "er", "isches"]:
                    state_id_mapping[state_name + variation] = state_id

        state_id = find_from_mapping(court_name, state_id_mapping)

        if state_id is not None:
            try:
                logger.debug("Look for state=%i, type=%s", state_id, court_type)
                return Court.objects.get(state_id=state_id, court_type=court_type)
            except Court.DoesNotExist:
                pass

        return None

    def _find_by_city(self, court_name: str, court_type: str) -> Optional[Court]:
        """Find court by city and type."""
        city_id_mapping = {}
        for city_id, city_name in City.objects.values_list("id", "name"):
            if city_name:
                city_id_mapping[city_name] = city_id

        city_id = find_from_mapping(court_name, city_id_mapping)

        if city_id is not None:
            try:
                logger.debug("Look for city=%i, type=%s", city_id, court_type)
                return Court.objects.get(city_id=city_id, court_type=court_type)
            except Court.DoesNotExist:
                pass

        return None

    def _find_by_alias(self, court_name: str) -> Optional[Court]:
        """Find court by alias (case-insensitive)."""
        candidates = Court.objects.filter(aliases__icontains=court_name)
        if len(candidates) == 1:
            return candidates.first()
        elif len(candidates) > 1:
            logger.warning(
                "Multiple court candidates found for '%s': %s",
                court_name,
                [c.name for c in candidates],
            )
        return None

    def resolve(
        self, court_name: str, court_code: Optional[str] = None
    ) -> Tuple[Court, Optional[str]]:
        """
        Resolve court from name, extracting chamber if present.

        This is the main entry point for court resolution.

        Args:
            court_name: Court name (may include chamber designation)
            court_code: Optional court code

        Returns:
            Tuple of (Court instance, chamber designation or None)

        Raises:
            CourtNotFoundError: If court cannot be resolved
        """
        # Extract chamber from name
        clean_name, chamber = self.remove_chamber(court_name)

        # Find the court
        court = self.find_court(clean_name, court_code)

        return court, chamber
