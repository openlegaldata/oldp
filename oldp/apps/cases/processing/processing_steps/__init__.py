from oldp.apps.cases.models import Case


class CaseProcessingStep(object):
    description = 'Case processing step without description'

    def __init__(self):
        super(CaseProcessingStep, self).__init__()

    def process(self, case: Case) -> Case:
        raise NotImplementedError('Abstract processing step needs to implement this method.')
