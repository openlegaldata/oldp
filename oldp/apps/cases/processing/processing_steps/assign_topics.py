import logging

from oldp.apps.cases.models import Case
from oldp.apps.cases.processing.processing_steps import CaseProcessingStep

logger = logging.getLogger(__name__)


class AssignTopics(CaseProcessingStep):
    description = 'Assign topics'
    # default_court = Court.objects.get(pk=Court.DEFAULT_ID)

    def __init__(self):
        super(AssignTopics, self).__init__()

    def process(self, case: Case):
        return case
