import logging

from oldp.apps.laws.models import Law, LawBook
from oldp.apps.laws.processing.processing_steps import LawBookProcessingStep

logger = logging.getLogger(__name__)


class ProcessingStep(LawBookProcessingStep):
    description = "Set review_status=accepted (cascades to child laws)"

    def process(self, law_book: LawBook):
        # Bulk review only promotes *pending* items; the cascade likewise
        # only touches pending laws, never rejected ones.
        if law_book.review_status != "pending":
            logger.info(
                "Skipping law book pk=%s: review_status=%s is not pending",
                law_book.pk,
                law_book.review_status,
            )
            return law_book
        law_book.review_status = "accepted"

        # Cascade to child Law rows. Without this, anonymous users see an
        # empty book because Law.get_queryset() filters out pending rows.
        if law_book.pk is not None:
            updated = Law.objects.filter(book=law_book, review_status="pending").update(
                review_status="accepted"
            )
            if updated:
                logger.info(
                    "Cascaded accepted to %d laws under book %s",
                    updated,
                    law_book.code,
                )

        return law_book
