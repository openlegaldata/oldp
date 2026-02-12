"""Law book creator service for creating law books with revision handling."""

import logging
from typing import Optional

from django.db import transaction
from django.utils.text import slugify

from oldp.apps.laws.exceptions import DuplicateLawBookError
from oldp.apps.laws.models import LawBook

logger = logging.getLogger(__name__)


class LawBookCreator:
    """Service for creating law books with automatic revision handling.

    This service handles:
    - Creating new law books
    - Managing the 'latest' flag across revisions
    - API token tracking
    """

    def check_duplicate(self, code: str, slug: str, revision_date) -> bool:
        """Check if a law book with the same code+revision_date or slug+revision_date exists.

        Args:
            code: Law book code
            slug: Law book slug
            revision_date: Revision date

        Returns:
            True if duplicate exists, False otherwise
        """
        return (
            LawBook.objects.filter(slug=slug, revision_date=revision_date).exists()
            or LawBook.objects.filter(code=code, revision_date=revision_date).exists()
        )

    @transaction.atomic
    def create_lawbook(
        self,
        code: str,
        title: str,
        revision_date,
        order: int = 0,
        changelog: Optional[str] = None,
        footnotes: Optional[str] = None,
        sections: Optional[str] = None,
        api_token=None,
    ) -> LawBook:
        """Create a new law book with automatic revision handling.

        If this revision is newer than existing revisions, it becomes the 'latest'.
        If there are existing 'latest' revisions and this is newer, they are updated.

        Args:
            code: Book code (e.g., "BGB", "StGB")
            title: Full title of the book
            revision_date: Date of this revision
            order: Display order (importance)
            changelog: JSON changelog string
            footnotes: JSON footnotes string
            sections: JSON sections string
            api_token: APIToken used for creation (for tracking)

        Returns:
            Created LawBook instance

        Raises:
            DuplicateLawBookError: If law book with same code+revision_date exists
        """
        # Generate slug from code
        slug = slugify(code)

        # Check for duplicates
        if self.check_duplicate(code, slug, revision_date):
            raise DuplicateLawBookError(
                f"A law book with code '{code}' and revision date '{revision_date}' already exists."
            )

        # Determine if this should be the latest revision
        existing_latest = LawBook.objects.filter(code=code, latest=True).first()

        # This revision is latest if:
        # 1. No existing books with this code, OR
        # 2. This revision_date is newer than the current latest
        is_latest = True
        if existing_latest and existing_latest.revision_date >= revision_date:
            # Existing latest is same or newer, this one is not latest
            is_latest = False

        # If this will be the latest, unset existing latest
        if is_latest and existing_latest:
            LawBook.objects.filter(code=code, latest=True).update(latest=False)
            logger.info(
                "Updated existing latest revision for %s (date=%s) to latest=False",
                code,
                existing_latest.revision_date,
            )

        # Create the law book
        lawbook = LawBook(
            code=code,
            title=title,
            slug=slug,
            revision_date=revision_date,
            latest=is_latest,
            order=order,
            changelog=changelog or "[]",
            footnotes=footnotes or "[]",
            sections=sections or "{}",
        )

        # Items created via API (with token) require manual approval
        if api_token is not None:
            from oldp.apps.accounts.models import APIToken

            if isinstance(api_token, APIToken):
                lawbook.created_by_token = api_token
                lawbook.review_status = "pending"

        lawbook.save()

        logger.info(
            "Created law book %s (id=%s, revision=%s, latest=%s)",
            code,
            lawbook.pk,
            revision_date,
            is_latest,
        )

        return lawbook
