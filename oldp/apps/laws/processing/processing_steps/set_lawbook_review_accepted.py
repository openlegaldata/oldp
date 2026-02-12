import logging

from oldp.apps.laws.models import LawBook
from oldp.apps.laws.processing.processing_steps import LawBookProcessingStep

logger = logging.getLogger(__name__)


class ProcessingStep(LawBookProcessingStep):
    description = "Set review_status=accepted"

    def process(self, law_book: LawBook):
        law_book.review_status = "accepted"

        return law_book
