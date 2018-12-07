from oldp.apps.processing.processing_steps import BaseProcessingStep
from oldp.apps.references.models import Reference


class ReferenceProcessingStep(BaseProcessingStep):
    description = 'Reference processing step without description'

    def __init__(self):
        super().__init__()

    def process(self, ref: Reference) -> Reference:
        raise NotImplementedError('Abstract processing step needs to implement this method.')
