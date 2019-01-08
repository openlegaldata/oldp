from abc import ABC, abstractmethod

from typing import Generator, Pattern

from oldp.apps.nlp.base import DocBase


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
        for match in self.regex_obj().finditer(doc.get_text()):
            yield (self.normalize(match.groupdict(), match.group(0)), match.start(), match.end())


class DocEntityStrategy(NERStrategy):

    def __init__(self, entity_type):
        self.entity_type = entity_type

    def extract(self, doc: DocBase) -> Generator:
        return doc.get_ents(self.entity_type)
