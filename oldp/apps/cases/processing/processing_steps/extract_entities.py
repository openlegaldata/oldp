import logging

from oldp.apps.cases.models import Case
from oldp.apps.cases.processing.processing_steps import CaseProcessingStep
from oldp.apps.nlp.models import Entity
from oldp.apps.processing.processing_steps.extract_entities import EntityProcessor, \
    get_text_from_html

logger = logging.getLogger(__name__)


class ProcessingStep(CaseProcessingStep, EntityProcessor):
    description = 'Extract entities'

    def __init__(self, entity_types=(Entity.MONEY,)):
        super().__init__()
        self.entity_types = entity_types

    def process(self, case: Case) -> Case:
        text = get_text_from_html(case.content)
        self.extract_and_load(text, case, lang='de')
        return case
