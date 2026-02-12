import logging

from oldp.apps.courts.models import Court
from oldp.apps.courts.processing import CourtProcessingStep

logger = logging.getLogger(__name__)


class ProcessingStep(CourtProcessingStep):
    description = "Set review_status=pending"

    def process(self, court: Court):
        court.review_status = "pending"

        return court
