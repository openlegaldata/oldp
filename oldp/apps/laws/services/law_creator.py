"""Law creator service for creating laws within law books."""

import logging
from typing import Optional

from django.utils.text import slugify

from oldp.apps.laws.exceptions import DuplicateLawError, LawBookNotFoundError
from oldp.apps.laws.models import Law, LawBook

logger = logging.getLogger(__name__)


class LawCreator:
    """Service for creating laws within law books.

    This service handles:
    - Law book resolution from code
    - Duplicate checking
    - API token tracking
    """

    def resolve_lawbook(
        self,
        book_code: str,
        revision_date=None,
        use_latest: bool = True,
    ) -> LawBook:
        """Resolve a law book from code and optional revision date.

        Args:
            book_code: Law book code (e.g., "BGB", "StGB")
            revision_date: Optional specific revision date
            use_latest: If True and no revision_date, use the latest revision

        Returns:
            LawBook instance

        Raises:
            LawBookNotFoundError: If law book cannot be found
        """
        if not book_code:
            raise LawBookNotFoundError("Book code is required")

        if revision_date:
            qs = LawBook.objects.filter(code=book_code, revision_date=revision_date)
        elif use_latest:
            qs = LawBook.objects.filter(code=book_code, latest=True)
        else:
            raise LawBookNotFoundError(
                "Either revision_date or use_latest=True is required"
            )

        book = qs.order_by("-pk").first()
        if book is None:
            if revision_date:
                raise LawBookNotFoundError(
                    f"Law book with code '{book_code}' and revision date '{revision_date}' not found"
                )
            else:
                raise LawBookNotFoundError(
                    f"No latest revision found for law book code '{book_code}'"
                )
        return book

    def check_duplicate(self, book: LawBook, slug: str) -> bool:
        """Check if a law with the same book and slug already exists.

        Args:
            book: LawBook instance
            slug: Law slug

        Returns:
            True if duplicate exists, False otherwise
        """
        return Law.objects.filter(book=book, slug=slug).exists()

    def create_law(
        self,
        book_code: str,
        section: str,
        title: str,
        content: str,
        revision_date=None,
        slug: Optional[str] = None,
        order: int = 0,
        amtabk: Optional[str] = None,
        kurzue: Optional[str] = None,
        doknr: Optional[str] = None,
        footnotes: Optional[str] = None,
        api_token=None,
    ) -> Law:
        """Create a new law within a law book.

        Args:
            book_code: Law book code (e.g., "BGB", "StGB")
            section: Section identifier (e.g., "§ 1", "Art. 1")
            title: Verbose title of the law
            content: Law content in HTML
            revision_date: Optional specific book revision date (uses latest if not specified)
            slug: Optional slug (auto-generated from section if not provided)
            order: Order within the book
            amtabk: Official abbreviation
            kurzue: Short title
            doknr: Document number from XML source
            footnotes: Footnotes as JSON array
            api_token: APIToken used for creation (for tracking)

        Returns:
            Created Law instance

        Raises:
            DuplicateLawError: If law with same book+slug exists
            LawBookNotFoundError: If law book cannot be found
        """
        # Resolve the law book
        book = self.resolve_lawbook(book_code, revision_date)

        # Generate slug from section if not provided
        if not slug:
            slug = slugify(section) if section else "untitled"

        # Check for duplicates
        if self.check_duplicate(book, slug):
            raise DuplicateLawError(
                f"A law with book '{book.code}' (revision {book.revision_date}) "
                f"and slug '{slug}' already exists."
            )

        # Create the law
        law = Law(
            book=book,
            section=section,
            title=title,
            content=content,
            slug=slug,
            order=order,
            amtabk=amtabk or "",
            kurzue=kurzue or "",
            doknr=doknr or "",
            footnotes=footnotes or "",
        )

        # Track the API token if provided
        if api_token is not None:
            from oldp.apps.accounts.models import APIToken

            if isinstance(api_token, APIToken):
                law.created_by_token = api_token
                law.review_status = "pending"

        law.save()

        logger.info(
            "Created law %s/%s (id=%s, section=%s)",
            book.code,
            slug,
            law.pk,
            section,
        )

        return law
