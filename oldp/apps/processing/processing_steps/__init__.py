

class BaseProcessingStep(object):
    description = 'Processing step without description'

    def process(self, content):
        raise NotImplementedError()
