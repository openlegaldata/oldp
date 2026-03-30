"""Court resolver service for resolving court from name/string input.

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
    """Service to resolve court from name/string input.

    This service extracts the court resolution logic from the assign_court
    processing step to allow reuse in the case creation API.
    """

    # Standalone suffixes stripped from court names before resolution.
    # These are chamber/division designations that appear as separate trailing words.
    CHAMBER_SUFFIXES = (
        "Einzelrichter",
        "Einzelrichterin",
        "Zivilabteilung",
        "Strafabteilung",
        "Familienabteilung",
        "Beschwerdesenat",
        "Vergabesenat",
    )

    def remove_chamber(self, name: str) -> Tuple[str, Optional[str]]:
        """Extract chamber designation from court name.

        Examples:
            - "LG Kiel Kammer für Handelssachen" -> ("LG Kiel", "Kammer für Handelssachen")
            - "LG Koblenz 14. Zivilkammer" -> ("LG Koblenz", "14. Zivilkammer")
            - "OLG Koblenz 2. Senat für Bußgeldsachen" -> ("OLG Koblenz", "2. Senat für Bußgeldsachen")
            - "AG Frankfurt Einzelrichter" -> ("AG Frankfurt", "Einzelrichter")

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

        # Strip standalone suffix words (e.g. "Einzelrichter", "Zivilabteilung")
        for suffix in self.CHAMBER_SUFFIXES:
            if name.endswith(" " + suffix):
                chamber = suffix
                name = name[: -(len(suffix) + 1)]
                break

        return name.strip(), chamber

    def find_court(self, court_name: str, court_code: Optional[str] = None) -> Court:
        """Find court by name, code, or alias.

        Resolution order:
        1. By code (if provided)
        2. By exact name match
        3. By exact code match
        4. By alias (case-insensitive, early — more precise than geographic)
        5. By court type + state location
        6. By court type + city location
        7. By partial name match

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

        # Try matching by court code (e.g. "BVerfG", "BGH")
        try:
            return Court.objects.get(code=court_name)
        except Court.DoesNotExist:
            pass

        # Try alias match early — aliases are more precise than geographic inference
        court = self._find_by_alias(court_name)
        if court:
            return court

        # Determine court type
        court_type = Court.extract_type_code_from_name(court_name)

        if court_type is None:
            raise CourtNotFoundError(
                f"Could not determine court type from name: {court_name}"
            )

        try:
            location_levels = settings.COURT_TYPES.get_type(court_type)["levels"]
        except (KeyError, TypeError):
            raise CourtNotFoundError(f"Unknown court type: {court_type}")

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

        # Try partial name match with court type filter (e.g. "VGH München" → type VGH, 1 match)
        if court_type:
            court = self._find_by_partial_name(court_name, court_type)
            if court:
                return court

        raise CourtNotFoundError(f"Could not resolve court from name: {court_name}")

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

    def _find_by_partial_name(
        self, court_name: str, court_type: str
    ) -> Optional[Court]:
        """Find court by extracting location words and matching against court names.

        For input like 'VGH München', extract 'München' and find courts of type VGH
        whose name contains 'München' or whose state contains a city named 'München'.
        Falls back to finding the court's state via City model.
        """
        # Extract the location part (everything after the court type prefix)
        words = court_name.split()
        location_parts = [w for w in words if w.upper() != court_type.upper()]
        if not location_parts:
            return None

        location = " ".join(location_parts)

        # Try direct name match: "VGH München" → courts of type VGH with "München" in name
        candidates = Court.objects.filter(
            court_type=court_type, name__icontains=location
        )
        if candidates.count() == 1:
            return candidates.first()

        # Try city → state resolution: München is in Bayern → find VGH in Bayern
        try:
            city = City.objects.get(name=location)
            if city.state_id:
                try:
                    return Court.objects.get(
                        court_type=court_type, state_id=city.state_id
                    )
                except Court.DoesNotExist:
                    pass
        except City.DoesNotExist:
            pass

        return None

    def _find_by_alias(self, court_name: str) -> Optional[Court]:
        """Find court by alias (case-insensitive).

        First tries icontains. If multiple candidates, narrows to exact line match.
        """
        candidates = Court.objects.filter(aliases__icontains=court_name)
        if len(candidates) == 1:
            return candidates.first()
        elif len(candidates) > 1:
            # Disambiguate: check for exact line match in aliases
            exact = [
                c
                for c in candidates
                if court_name.lower()
                in [a.strip().lower() for a in (c.aliases or "").splitlines()]
            ]
            if len(exact) == 1:
                return exact[0]
            logger.warning(
                "Multiple court candidates found for '%s': %s",
                court_name,
                [c.name for c in candidates],
            )
        return None

    def resolve(
        self, court_name: str, court_code: Optional[str] = None
    ) -> Tuple[Court, Optional[str]]:
        """Resolve court from name, extracting chamber if present.

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
