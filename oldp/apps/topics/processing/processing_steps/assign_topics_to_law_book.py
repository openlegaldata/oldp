import random

from oldp.apps.laws.models import LawBook
from oldp.apps.laws.processing.processing_steps import LawBookProcessingStep
from oldp.apps.topics.models import Topic


class ProcessingStep(LawBookProcessingStep):
    description = 'Assign topics'

    def __init__(self):
        super().__init__()

        self.topics = Topic.objects.all()

    def process(self, law_book: LawBook) -> LawBook:
        # Remove existing topics
        law_book.topics.clean()

        # Select 5 random topics
        for t in random.sample(self.topics, 5):
            law_book.topics.add(t)

        law_book.save()

        return law_book
