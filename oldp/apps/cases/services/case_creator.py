"""Case creator service for creating cases with automatic FK resolution and processing."""

import logging
from typing import Optional

from oldp.apps.cases.exceptions import DuplicateCaseError
from oldp.apps.cases.models import Case
from oldp.apps.cases.services.court_resolver import CourtResolver
from oldp.apps.sources.models import Source

logger = logging.getLogger(__name__)


class CaseCreator:
    """Service for creating cases with automatic FK resolution and processing.

    This service encapsulates the case creation logic including:
    - Court resolution from name
    - Duplicate checking
    - Reference extraction
    - API token tracking
    """

    def __init__(
        self,
        court_resolver: Optional[CourtResolver] = None,
        extract_refs: bool = True,
    ):
        """Initialize the case creator.

        Args:
            court_resolver: Optional CourtResolver instance (creates default if None)
            extract_refs: Whether to extract references on creation (default: True)
        """
        self.court_resolver = court_resolver or CourtResolver()
        self.extract_refs = extract_refs

    def check_duplicate(self, court, file_number: str) -> bool:
        """Check if a case with the same court and file_number already exists.

        Args:
            court: Court instance
            file_number: Case file number

        Returns:
            True if duplicate exists, False otherwise
        """
        return Case.objects.filter(court=court, file_number=file_number).exists()

    def _extract_references(self, case: Case) -> Case:
        """Extract law and case references from case content.

        Args:
            case: Case instance with content

        Returns:
            Case instance with references extracted
        """
        from oldp.apps.cases.processing.processing_steps.extract_refs import (
            ProcessingStep as ExtractRefsStep,
        )

        try:
            step = ExtractRefsStep(
                law_refs=True,
                case_refs=True,
                assign_refs=True,
            )
            return step.process(case)
        except Exception as e:
            logger.warning("Failed to extract references for case %s: %s", case.pk, e)
            return case

    def resolve_source(
        self,
        source_name: str,
        source_homepage: str = "",
    ) -> Source:
        """Resolve a source by name, creating it if it does not exist.

        Lookup is based on name only. Homepage is used only when creating a
        new source.

        Args:
            source_name: Name of the source to look up or create.
            source_homepage: Homepage URL, used as default when creating.

        Returns:
            Source instance.
        """
        source, created = Source.objects.get_or_create(
            name=source_name,
            defaults={"homepage": source_homepage or ""},
        )
        if created:
            logger.info("Created new source: %s (id=%s)", source.name, source.pk)
        return source

    def create_case(
        self,
        court_name: str,
        file_number: str,
        date,
        content: str,
        case_type: Optional[str] = None,
        ecli: Optional[str] = None,
        abstract: Optional[str] = None,
        title: Optional[str] = None,
        court_code: Optional[str] = None,
        api_token=None,
        extract_refs: Optional[bool] = None,
        source_name: Optional[str] = None,
        source_homepage: Optional[str] = None,
    ) -> Case:
        """Create a new case with automatic processing.

        Args:
            court_name: Name of the court (will be resolved to Court FK)
            file_number: Court file number
            date: Publication date
            content: Full case content in HTML
            case_type: Type of decision (e.g., "Urteil", "Beschluss")
            ecli: European Case Law Identifier
            abstract: Case summary in HTML
            title: Case title
            court_code: Optional court code for resolution
            api_token: APIToken used for creation (for tracking)
            extract_refs: Whether to extract references (overrides instance setting)
            source_name: Optional source name for lookup/creation
            source_homepage: Optional homepage URL for new source creation

        Returns:
            Created Case instance

        Raises:
            DuplicateCaseError: If case with same court+file_number exists
            CourtNotFoundError: If court cannot be resolved
        """
        # Resolve court from name
        court, chamber = self.court_resolver.resolve(court_name, court_code)

        # Check for duplicates
        if self.check_duplicate(court, file_number):
            raise DuplicateCaseError(
                f"A case with court '{court.name}' and file number '{file_number}' already exists."
            )

        # Resolve source
        if source_name:
            source = self.resolve_source(source_name, source_homepage or "")
        else:
            source = Source.objects.get(pk=Source.DEFAULT_ID)

        # Cases created via API (with token) require manual approval
        review_status = "accepted"
        if api_token is not None:
            review_status = "pending"

        # Create the case
        case = Case(
            court=court,
            court_chamber=chamber,
            file_number=file_number,
            date=date,
            content=content,
            type=case_type,
            ecli=ecli or "",
            abstract=abstract or "",
            title=title or "",
            review_status=review_status,
            source=source,
        )

        # Set the slug based on court and date
        case.set_slug()

        # Track the API token if provided
        if api_token is not None:
            case.created_by_token = api_token

        # Save the case first (required for reference extraction)
        case.save()

        # Extract references if enabled
        should_extract = extract_refs if extract_refs is not None else self.extract_refs
        if should_extract:
            case = self._extract_references(case)
            case.save()

        logger.info(
            "Created case %s (id=%s, court=%s, file_number=%s)",
            case.slug,
            case.pk,
            court.code,
            file_number,
        )

        return case
