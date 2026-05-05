import logging

from oldp.apps.laws.models import Law, LawBook
from oldp.apps.laws.processing.processing_steps import LawBookProcessingStep

logger = logging.getLogger(__name__)


class ProcessingStep(LawBookProcessingStep):
    description = "Set review_status=pending (cascades to child laws)"

    def process(self, law_book: LawBook):
        law_book.review_status = "pending"

        # Cascade to child Law rows so visibility stays consistent with the
        # book. Otherwise un-accepting a book leaves its laws publicly visible.
        if law_book.pk is not None:
            updated = (
                Law.objects.filter(book=law_book)
                .exclude(review_status="pending")
                .update(review_status="pending")
            )
            if updated:
                logger.info(
                    "Cascaded pending to %d laws under book %s",
                    updated,
                    law_book.code,
                )

        return law_book
