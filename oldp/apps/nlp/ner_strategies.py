from abc import ABC, abstractmethod

from typing import Generator, Pattern

from oldp.apps.nlp.base import Content
import oldp.apps.nlp.regexps as regex


class NERStrategy(ABC):

    def __init__(self, lang):
        self.lang = lang

    @abstractmethod
    def extract(self, content: Content) -> Generator:
        pass


class RegexStrategy(NERStrategy):

    @abstractmethod
    def regex_obj(self) -> Pattern:
        pass

    def extract(self, content: Content) -> Generator:
        for match in self.regex_obj().finditer(content.get_text()):
            yield (match.group(0), match.start(), match.end())


class NLPStrategy(NERStrategy):

    def extract(self, content: Content) -> Generator:
        pass


class UniversalMoneyExtractionStrategy(RegexStrategy):
    # only supports euro so far

    def regex_obj(self):
        return regex.euro_amount()
