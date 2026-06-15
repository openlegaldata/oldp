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

        # Create the law book. The ``latest`` flag is NOT decided here — it is
        # owned by ``LawBook.refresh_latest_for_code`` and tracks the newest
        # *accepted* revision. Creating it ``latest=False`` up front means an
        # unapproved (pending) submission never demotes the currently-published
        # revision; the flag flips only once this revision is accepted.
        lawbook = LawBook(
            code=code,
            title=title,
            slug=slug,
            revision_date=revision_date,
            latest=False,
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

        # Re-establish the latest invariant. For a directly-accepted revision
        # (no API token) this promotes it when it is the newest accepted one,
        # demoting the previous latest — preserving the prior behaviour. For a
        # pending API submission it is a no-op on the published revision.
        LawBook.refresh_latest_for_code(code)
        lawbook.refresh_from_db(fields=["latest"])

        logger.info(
            "Created law book %s (id=%s, revision=%s, review_status=%s, latest=%s)",
            code,
            lawbook.pk,
            revision_date,
            lawbook.review_status,
            lawbook.latest,
        )

        return lawbook
