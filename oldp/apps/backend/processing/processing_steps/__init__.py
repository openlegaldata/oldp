

class BaseProcessingStep(object):
    pass

    def process(self, content):
        raise NotImplementedError()
