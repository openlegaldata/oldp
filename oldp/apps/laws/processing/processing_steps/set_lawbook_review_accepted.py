import logging

from oldp.apps.laws.models import Law, LawBook
from oldp.apps.laws.processing.processing_steps import LawBookProcessingStep

logger = logging.getLogger(__name__)


class ProcessingStep(LawBookProcessingStep):
    description = "Set review_status=accepted (cascades to child laws)"

    def process(self, law_book: LawBook):
        law_book.review_status = "accepted"

        # Cascade to child Law rows. Without this, anonymous users see an
        # empty book because Law.get_queryset() filters out pending rows.
        if law_book.pk is not None:
            updated = (
                Law.objects.filter(book=law_book)
                .exclude(review_status="accepted")
                .update(review_status="accepted")
            )
            if updated:
                logger.info(
                    "Cascaded accepted to %d laws under book %s",
                    updated,
                    law_book.code,
                )

        return law_book
