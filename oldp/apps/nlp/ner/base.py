from typing import Generator

from oldp.apps.nlp.base import SpacyNLP
from oldp.apps.nlp.ner.strategy_factories import UniversalNERStrategyFactory


class EntityExtractor:

    def __init__(self, lang='de'):
        self.doc = None
        self.factory = UniversalNERStrategyFactory(lang)

    def prepare(self, text):
        nlp = SpacyNLP()
        self.doc = nlp.process(text)

    def extract(self, entity_type) -> Generator:
        strategy = self.factory.get_strategy(entity_type)
        return strategy.extract(self.doc)
