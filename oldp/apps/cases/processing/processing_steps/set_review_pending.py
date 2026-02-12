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
        case.review_status = "pending"

        return case
