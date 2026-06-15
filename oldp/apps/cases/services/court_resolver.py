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

# ECLI court segment: ``ECLI:DE:<court>:<year>:<ordinal>``. The third field is
# the issuing court's abbreviation (e.g. "BGH", "BVerfG", "VFGHNRW") and, for
# the federal courts that dominate the unresolved-court cases, equals the OLDP
# ``Court.code``. Used as a last-resort fallback so a case with an unmatched
# free-text court name is still attributed to the right court instead of the
# "unknown" placeholder (audit A4 — the lasting, ingestion-side fix).
_ECLI_COURT_RE = re.compile(r"^ECLI:DE:(?P<court>[A-Za-z0-9]+):", re.IGNORECASE)


def court_code_from_ecli(ecli: Optional[str]) -> Optional[str]:
    """Return the court abbreviation embedded in a German ECLI, or ``None``.

    ``ECLI:DE:BGH:2022:...`` -> ``"BGH"``. Mirrors
    ``oldp_ingestor.court_analysis.court_code_from_ecli`` (re-implemented to
    avoid a cross-package dependency).
    """
    if not ecli:
        return None
    m = _ECLI_COURT_RE.match(ecli.strip())
    return m.group("court") if m else None


def _lookup_one(**filters) -> Optional[Court]:
    """Look up a single Court by exact-match filters.

    Returns the Court when exactly one matches; returns ``None`` for both
    "no matches" and "multiple matches". The caller should treat ``None``
    as "this resolution strategy was inconclusive" and fall through to
    the next. Ambiguous results are logged at WARNING so data-quality
    issues surface in logs without breaking the API.

    Catching ``MultipleObjectsReturned`` here is what keeps an ambiguous
    name (two ``Court`` rows sharing ``name``) from leaking out of
    ``CourtResolver.find_court`` as an uncaught 500. See PR for the
    incident where dev → prod case migration tripped on two
    "Hanseatisches Oberlandesgericht" rows (Bremen + Hamburg).
    """
    try:
        return Court.objects.get(**filters)
    except Court.DoesNotExist:
        return None
    except Court.MultipleObjectsReturned:
        logger.warning(
            "Ambiguous court lookup %s — multiple rows match; "
            "falling through to next resolution strategy",
            filters,
        )
        return None


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

    def find_court(
        self,
        court_name: str,
        court_code: Optional[str] = None,
        ecli: Optional[str] = None,
    ) -> Court:
        """Find court by name, code, alias, or (last resort) ECLI.

        Resolution order:
        1. By code (if provided)
        2. By exact name match
        3. By exact code match
        4. By alias (case-insensitive, early — more precise than geographic)
        5. By court type + state location
        6. By court type + city location
        7. By partial name match
        8. By the court code embedded in the ECLI (last resort)

        Args:
            court_name: Court name to search for
            court_code: Optional court code (e.g., "EuGH", "BGH")
            ecli: Optional ECLI; its court segment is used as a final fallback.

        Returns:
            Court instance

        Raises:
            CourtNotFoundError: If court cannot be resolved
        """
        # Try to find by code first
        if court_code:
            court = _lookup_one(code=court_code)
            if court:
                return court

        if not court_name:
            court = self._find_by_ecli(ecli)
            if court:
                return court
            raise CourtNotFoundError("Court name is required")

        # Handle special case for EU court
        if court_name == "EU":
            court = _lookup_one(code="EuGH")
            if court:
                return court

        # Try exact name match first
        court = _lookup_one(name=court_name)
        if court:
            return court

        # Try matching by court code (e.g. "BVerfG", "BGH")
        court = _lookup_one(code=court_name)
        if court:
            return court

        # Try alias match early — aliases are more precise than geographic inference
        court = self._find_by_alias(court_name)
        if court:
            return court

        # Determine court type
        court_type = Court.extract_type_code_from_name(court_name)

        if court_type is None:
            court = self._find_by_ecli(ecli)
            if court:
                return court
            raise CourtNotFoundError(
                f"Could not determine court type from name: {court_name}"
            )

        try:
            location_levels = settings.COURT_TYPES.get_type(court_type)["levels"]
        except (KeyError, TypeError):
            court = self._find_by_ecli(ecli)
            if court:
                return court
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

        # Last resort: the court code embedded in the ECLI. Prevents an
        # unmatched free-text name from defaulting the case to the "unknown"
        # court when the ECLI still names the issuing court.
        court = self._find_by_ecli(ecli)
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
            logger.debug("Look for state=%i, type=%s", state_id, court_type)
            court = _lookup_one(state_id=state_id, court_type=court_type)
            if court:
                return court

        return None

    def _find_by_city(self, court_name: str, court_type: str) -> Optional[Court]:
        """Find court by city and type."""
        city_id_mapping = {}
        for city_id, city_name in City.objects.values_list("id", "name"):
            if city_name:
                city_id_mapping[city_name] = city_id

        city_id = find_from_mapping(court_name, city_id_mapping)

        if city_id is not None:
            logger.debug("Look for city=%i, type=%s", city_id, court_type)
            court = _lookup_one(city_id=city_id, court_type=court_type)
            if court:
                return court

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
        except City.DoesNotExist:
            return None
        except City.MultipleObjectsReturned:
            logger.warning(
                "Ambiguous city lookup name=%r in _find_by_partial_name; "
                "falling through",
                location,
            )
            return None
        if city.state_id:
            court = _lookup_one(court_type=court_type, state_id=city.state_id)
            if court:
                return court

        return None

    def _find_by_ecli(self, ecli: Optional[str]) -> Optional[Court]:
        """Resolve a court from the abbreviation embedded in an ECLI.

        Looks the ECLI court segment up against ``Court.code`` (case-insensitive).
        Returns ``None`` when there is no ECLI, no court segment, or no/ambiguous
        matching court — the caller then falls through to its normal failure.
        """
        code = court_code_from_ecli(ecli)
        if not code:
            return None
        court = _lookup_one(code__iexact=code)
        if court:
            logger.debug("Resolved court %s from ECLI %s", court.code, ecli)
        return court

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
        self,
        court_name: str,
        court_code: Optional[str] = None,
        ecli: Optional[str] = None,
    ) -> Tuple[Court, Optional[str]]:
        """Resolve court from name, extracting chamber if present.

        This is the main entry point for court resolution.

        Args:
            court_name: Court name (may include chamber designation)
            court_code: Optional court code
            ecli: Optional ECLI used as a last-resort court-code fallback.

        Returns:
            Tuple of (Court instance, chamber designation or None)

        Raises:
            CourtNotFoundError: If court cannot be resolved
        """
        # Extract chamber from name
        clean_name, chamber = self.remove_chamber(court_name or "")

        # Find the court
        court = self.find_court(clean_name, court_code, ecli=ecli)

        return court, chamber
