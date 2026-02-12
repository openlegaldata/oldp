"""Court creator service for creating courts with state/city resolution."""

import logging
from typing import Optional

from django.db import transaction

from oldp.apps.courts.exceptions import DuplicateCourtError, StateNotFoundError
from oldp.apps.courts.models import City, Court, State

logger = logging.getLogger(__name__)


class CourtCreator:
    """Service for creating courts with automatic state/city resolution.

    This service handles:
    - Resolving state from name
    - Resolving or creating city from name + state
    - Duplicate detection by court code
    - API token tracking
    - Review status management
    """

    def resolve_state(self, state_name: str) -> State:
        """Resolve state from name (case-insensitive lookup).

        Args:
            state_name: Name of the state to resolve.

        Returns:
            State instance.

        Raises:
            StateNotFoundError: If the state cannot be found.
        """
        # Try exact match first
        try:
            return State.objects.get(name=state_name)
        except State.DoesNotExist:
            pass

        # Try case-insensitive match
        try:
            return State.objects.get(name__iexact=state_name)
        except State.DoesNotExist:
            raise StateNotFoundError(
                f"Could not resolve state from the provided name: '{state_name}'."
            )
        except State.MultipleObjectsReturned:
            # If multiple matches, return the first one
            return State.objects.filter(name__iexact=state_name).first()

    def resolve_city(self, city_name: str, state: State) -> Optional[City]:
        """Resolve city from name within a state. Creates city if not found.

        Args:
            city_name: Name of the city to resolve. If empty, returns None.
            state: State the city belongs to.

        Returns:
            City instance or None if city_name is not provided.
        """
        if not city_name:
            return None

        # Try exact match within state
        try:
            return City.objects.get(name=city_name, state=state)
        except City.DoesNotExist:
            pass

        # Try case-insensitive match within state
        try:
            return City.objects.get(name__iexact=city_name, state=state)
        except City.DoesNotExist:
            pass
        except City.MultipleObjectsReturned:
            return City.objects.filter(name__iexact=city_name, state=state).first()

        # Create city if not found (cities are less critical reference data)
        city = City(name=city_name, state=state)
        city.save()
        logger.info("Created new city '%s' in state '%s'", city_name, state.name)
        return city

    def check_duplicate(self, code: str) -> bool:
        """Check if court with same code exists.

        Args:
            code: Court code to check.

        Returns:
            True if duplicate exists, False otherwise.
        """
        return Court.objects.filter(code=code).exists()

    @transaction.atomic
    def create_court(
        self,
        name: str,
        code: str,
        state_name: str,
        court_type: Optional[str] = None,
        city_name: Optional[str] = None,
        jurisdiction: Optional[str] = None,
        level_of_appeal: Optional[str] = None,
        aliases: Optional[str] = None,
        description: Optional[str] = None,
        homepage: Optional[str] = None,
        street_address: Optional[str] = None,
        postal_code: Optional[str] = None,
        address_locality: Optional[str] = None,
        telephone: Optional[str] = None,
        fax_number: Optional[str] = None,
        email: Optional[str] = None,
        api_token=None,
    ) -> Court:
        """Create a new court with automatic state/city resolution.

        Args:
            name: Full name of the court.
            code: Unique court code (e.g., "BVerfG").
            state_name: State name for resolution.
            court_type: Court type code (e.g., "AG", "LG").
            city_name: City name for resolution (optional).
            jurisdiction: Jurisdiction of court.
            level_of_appeal: Level of appeal.
            aliases: List of aliases (one per line).
            description: Court description.
            homepage: Official court homepage URL.
            street_address: Street address.
            postal_code: Postal code.
            address_locality: Address locality.
            telephone: Telephone number.
            fax_number: Fax number.
            email: Email address.
            api_token: APIToken used for creation (for tracking).

        Returns:
            Created Court instance.

        Raises:
            DuplicateCourtError: If court with same code exists.
            StateNotFoundError: If state cannot be resolved.
        """
        # 1. Resolve state
        state = self.resolve_state(state_name)

        # 2. Resolve city (optional)
        city = self.resolve_city(city_name, state) if city_name else None

        # 3. Check duplicate by code
        if self.check_duplicate(code):
            raise DuplicateCourtError(f"A court with code '{code}' already exists.")

        # 4. Create the court
        court = Court(
            name=name,
            code=code,
            state=state,
            city=city,
            court_type=court_type or None,
            jurisdiction=jurisdiction or None,
            level_of_appeal=level_of_appeal or None,
            aliases=aliases or None,
            description=description or "",
            homepage=homepage or None,
            street_address=street_address or None,
            postal_code=postal_code or None,
            address_locality=address_locality or None,
            telephone=telephone or None,
            fax_number=fax_number or None,
            email=email or None,
        )

        # 5. Set review_status based on API token
        if api_token is not None:
            court.review_status = "pending"

            from oldp.apps.accounts.models import APIToken

            if isinstance(api_token, APIToken):
                court.created_by_token = api_token

        # 6. Slug auto-generated by existing pre_save signal
        # 7. Save and return
        court.save()

        logger.info(
            "Created court %s (id=%s, code=%s, review_status=%s)",
            name,
            court.pk,
            code,
            court.review_status,
        )

        return court
