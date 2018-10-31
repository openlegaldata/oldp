from oldp.apps.laws.models import Law, LawBook
from oldp.apps.processing.processing_steps import BaseProcessingStep


class LawProcessingStep(BaseProcessingStep):
    description = 'Law processing step without description'

    def __init__(self):
        super().__init__()

    def process(self, law: Law) -> Law:
        raise NotImplementedError('Abstract processing step needs to implement this method.')


class LawBookProcessingStep(BaseProcessingStep):
    description = 'Law book processing step without description'

    def __init__(self):
        super().__init__()

    def process(self, law_book: LawBook) -> LawBook:
        raise NotImplementedError('Abstract processing step needs to implement this method.')
