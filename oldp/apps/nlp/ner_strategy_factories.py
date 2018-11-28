from abc import ABC, abstractmethod

from oldp.apps.nlp.models import Entity
from oldp.apps.nlp.ner_strategies import UniversalMoneyExtractionStrategy, NERStrategy


class NERStrategyFactory(ABC):

    def __init__(self, lang):
        self.lang = lang

    @abstractmethod
    def get_strategy(self, entity_type):
        pass


class UniversalNERStrategyFactory(NERStrategyFactory):

    def get_strategy(self, entity_type) -> NERStrategy:
        if entity_type == Entity.MONEY:
            return UniversalMoneyExtractionStrategy(self.lang)
        else:
            raise NotImplementedError('Strategy for type {} not implemented!'.format(entity_type))
