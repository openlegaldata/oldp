from oldp.apps.laws.models import Law
from oldp.apps.processing.processing_steps import BaseProcessingStep


class LawProcessingStep(BaseProcessingStep):
    description = 'Law processing step without description'

    def __init__(self):
        super(LawProcessingStep, self).__init__()

    def process(self, law: Law) -> Law:
        raise NotImplementedError('Abstract processing step needs to implement this method.')
