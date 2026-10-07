import logging

from oldp.apps.laws.models import Law
from oldp.apps.laws.processing.processing_steps import LawProcessingStep

logger = logging.getLogger(__name__)


class ProcessingStep(LawProcessingStep):
    description = "Set review_status=accepted"

    def process(self, law: Law):
        # Bulk review only promotes *pending* items.
        if law.review_status != "pending":
            logger.info(
                "Skipping law pk=%s: review_status=%s is not pending",
                law.pk,
                law.review_status,
            )
            return law
        law.review_status = "accepted"

        return law
