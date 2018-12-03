from oldp.apps.courts.models import Court
from oldp.apps.processing.processing_steps import BaseProcessingStep


class CourtProcessingStep(BaseProcessingStep):
    description = 'Court processing step without description'

    def __init__(self):
        super().__init__()

    def process(self, court: Court) -> Court:
        raise NotImplementedError('Abstract processing step needs to implement this method.')
