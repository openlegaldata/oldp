import logging

from oldp.apps.laws.models import Law
from oldp.apps.laws.processing.processing_steps import LawProcessingStep

logger = logging.getLogger(__name__)


class ProcessingStep(LawProcessingStep):
    description = "Set review_status=pending"

    def process(self, law: Law):
        law.review_status = "pending"

        return law
