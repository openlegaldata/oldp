import logging

from oldp.apps.cases.models import Case
from oldp.apps.cases.processing.processing_steps import CaseProcessingStep
from oldp.apps.search.processing.processing_steps.generate_related import (
    BaseGenerateRelated,
)

logger = logging.getLogger(__name__)


class ProcessingStep(CaseProcessingStep, BaseGenerateRelated):
    description = "Set review_status=pending"

    def process(self, case: Case):
        # Resetting to pending is allowed for accepted items (re-review), but
        # never for rejected ones: a case may have been rejected by hand, and
        # pending -> accepted would re-publish it through bulk approval.
        if case.review_status == "rejected":
            logger.info("Skipping rejected case pk=%s: not reset to pending", case.pk)
            return case
        case.review_status = "pending"

        return case
