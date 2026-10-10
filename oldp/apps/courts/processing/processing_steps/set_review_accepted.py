import logging

from oldp.apps.courts.models import Court
from oldp.apps.courts.processing import CourtProcessingStep

logger = logging.getLogger(__name__)


class ProcessingStep(CourtProcessingStep):
    description = "Set review_status=accepted"

    def process(self, court: Court):
        # Bulk review only promotes *pending* items; accepted/rejected courts
        # are never touched by bulk steps.
        if court.review_status != "pending":
            logger.info(
                "Skipping court pk=%s: review_status=%s is not pending",
                court.pk,
                court.review_status,
            )
            return court
        court.review_status = "accepted"

        return court
