from typing import Generator

from oldp.apps.nlp.base import SpacyNLP
from oldp.apps.nlp.ner.strategy_factories import UniversalNERStrategyFactory
from oldp.apps.nlp.preprocessing import HtmlConcealer


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


class HtmlEntityExtractor(EntityExtractor):
    html_concealer = None

    def prepare(self, text):
        self.html_concealer = HtmlConcealer(text)
        self.html_concealer.conceal()
        text = self.html_concealer.get_content()
        super().prepare(text)

    def extract(self, entity_type) -> Generator:
        for (value, start, end) in super().extract(entity_type):
            start, end = self.html_concealer.concealed_to_html_pos(start, end)
            yield value, start, end
