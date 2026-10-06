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
        if case.is_moderated:
            # A takedown/redaction record blocks re-publication; staff must
            # clear ``moderated_at`` deliberately first (see docs/content-moderation.md).
            logger.warning(
                "Refusing to accept moderated case pk=%s (moderated_at=%s)",
                case.pk,
                case.moderated_at,
            )
            return case
        case.review_status = "accepted"

        return case
