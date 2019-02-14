from abc import ABC, abstractmethod

from typing import Generator, Pattern

from oldp.apps.nlp.base import DocBase, SpacyDoc
from oldp.apps.nlp.ner.entity_relations import extract_relations


class NERStrategy(ABC):

    @abstractmethod
    def extract(self, doc: DocBase) -> Generator:
        pass


class RegexStrategy(NERStrategy):

    @abstractmethod
    def regex_obj(self) -> Pattern:
        pass

    def normalize(self, groups: dict, full_match: str) -> any:
        return full_match

    def extract(self, doc: DocBase) -> Generator:
        for match in self.regex_obj().finditer(doc.text):
            yield (self.normalize(match.groupdict(), match.group(0)), match.start(), match.end())


class DocEntityStrategy(NERStrategy):

    def __init__(self, entity_type):
        self.entity_type = entity_type

    def extract(self, doc: DocBase) -> Generator:
        return doc.ents(self.entity_type)


class SpacyDocEntityStrategy(DocEntityStrategy):

    def extract_with_relations(self, doc: SpacyDoc) -> Generator:
        return extract_relations(doc.doc, doc.spacy_entity_name(self.entity_type), doc.model.name())
