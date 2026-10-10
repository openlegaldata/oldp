import logging

from oldp.apps.cases.models import Case
from oldp.apps.cases.processing.processing_steps import CaseProcessingStep
from oldp.apps.search.processing.processing_steps.generate_related import (
    BaseGenerateRelated,
)

logger = logging.getLogger(__name__)


class ProcessingStep(CaseProcessingStep, BaseGenerateRelated):
    description = "Set review_status=rejected"

    def process(self, case: Case):
        # Bulk review only acts on *pending* items (see set_review_accepted).
        if case.review_status != "pending":
            logger.info(
                "Skipping case pk=%s: review_status=%s is not pending",
                case.pk,
                case.review_status,
            )
            return case
        case.review_status = "rejected"

        return case
