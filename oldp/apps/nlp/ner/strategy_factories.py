from abc import ABC, abstractmethod

from oldp.apps.nlp.models import Entity
from oldp.apps.nlp.ner.strategies import base, money, percents


class NERStrategyFactory(ABC):

    def __init__(self, lang):
        self.lang = lang

    @abstractmethod
    def get_strategy(self, entity_type) -> base.NERStrategy:
        pass


class UniversalNERStrategyFactory(NERStrategyFactory):

    def get_strategy(self, entity_type) -> base.NERStrategy:
        if entity_type is Entity.MONEY and self.lang is 'de':
            return money.GermanCurrencyExtractionStrategy()
        elif entity_type is Entity.EURO and self.lang is 'de':
            return money.GermanEuroExtractionStrategy()
        elif entity_type is Entity.PERCENT and self.lang is 'de':
            return percents.GermanPercentageExtractionStrategy()
        elif entity_type in [Entity.PERSON, Entity.LOCATION, Entity.ORGANIZATION]:
            return base.DocEntityStrategy(entity_type)
        else:
            raise NotImplementedError('Strategy for type {} and language {} not '
                                      'implemented!'.format(entity_type, self.lang))


class LawNERStrategyFactory(UniversalNERStrategyFactory):

    def get_strategy(self, entity_type) -> base.NERStrategy:
        # if entity_type == Entity.LawSpecificEntity:
        #     return LawSpecificStrategy(self.lang)
        # else:
        return super(LawNERStrategyFactory, self).get_strategy(entity_type)


class CaseNERStrategyFactory(UniversalNERStrategyFactory):

    def get_strategy(self, entity_type) -> base.NERStrategy:
        # if entity_type == Entity.CaseSpecificEntity:
        #     return CaseSpecificStrategy(self.lang)
        # else:
        return super(CaseNERStrategyFactory, self).get_strategy(entity_type)
