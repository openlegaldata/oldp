import logging

from oldp.apps.laws.models import Law
from oldp.apps.laws.processing.processing_steps import LawProcessingStep

logger = logging.getLogger(__name__)


class ProcessingStep(LawProcessingStep):
    description = "Set review_status=pending"

    def process(self, law: Law):
        # Rejected items are never reset by bulk steps.
        if law.review_status == "rejected":
            logger.info("Skipping rejected law pk=%s: not reset to pending", law.pk)
            return law
        law.review_status = "pending"

        return law
