import logging

from oldp.apps.courts.models import Court
from oldp.apps.courts.processing import CourtProcessingStep

logger = logging.getLogger(__name__)


class ProcessingStep(CourtProcessingStep):
    description = "Set review_status=pending"

    def process(self, court: Court):
        # Rejected items are never reset by bulk steps (see cases).
        if court.review_status == "rejected":
            logger.info("Skipping rejected court pk=%s: not reset to pending", court.pk)
            return court
        court.review_status = "pending"

        return court
