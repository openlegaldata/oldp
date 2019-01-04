import logging

from oldp.apps.cases.models import Case, RelatedCase
from oldp.apps.cases.processing.processing_steps import CaseProcessingStep
from oldp.apps.search.processing import RelatedContentFinder
from oldp.apps.search.processing.processing_steps.generate_related import BaseGenerateRelated

logger = logging.getLogger(__name__)


class ProcessingStep(CaseProcessingStep, BaseGenerateRelated):
    description = 'Generate related cases'

    def __init__(self):
        super().__init__()

        # Initialize finder class with content model and relation model
        self.finder = RelatedContentFinder(Case, RelatedCase)

    def process(self, case: Case):

        self.finder.handle_item(case)

        return case
