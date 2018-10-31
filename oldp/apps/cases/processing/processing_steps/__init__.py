from oldp.apps.cases.models import Case
from oldp.apps.processing.processing_steps import BaseProcessingStep


class CaseProcessingStep(BaseProcessingStep):
    description = 'Case processing step without description'

    def __init__(self):
        super(CaseProcessingStep, self).__init__()

    def process(self, case: Case) -> Case:
        raise NotImplementedError('Abstract processing step needs to implement this method.')
