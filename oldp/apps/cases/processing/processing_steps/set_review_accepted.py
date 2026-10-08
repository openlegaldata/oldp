import logging

from oldp.apps.cases.models import Case
from oldp.apps.cases.processing.processing_steps import CaseProcessingStep
from oldp.apps.search.processing.processing_steps.generate_related import (
    BaseGenerateRelated,
)

logger = logging.getLogger(__name__)


class ProcessingStep(CaseProcessingStep, BaseGenerateRelated):
    description = "Set review_status=accepted"

    def process(self, case: Case):
        # Bulk review only promotes *pending* items. Already accepted or
        # rejected cases (e.g. rejected by hand after a privacy report) are never
        # touched by bulk steps; changing those is a deliberate single edit.
        if case.review_status != "pending":
            logger.info(
                "Skipping case pk=%s: review_status=%s is not pending",
                case.pk,
                case.review_status,
            )
            return case
        case.review_status = "accepted"

        return case
