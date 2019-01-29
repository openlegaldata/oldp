from abc import ABC, abstractmethod
from typing import Iterable

import nltk
from spacy.tokens import Doc

from oldp.apps.nlp.language_models import GermanSpacyModel, EnglishSpacyModel, SpacyModel


class DocBase(ABC):
    text = None

    @abstractmethod
    def tokens(self) -> [str]:
        pass

    @abstractmethod
    def lemmas(self) -> [str]:
        pass

    @abstractmethod
    def ents(self, entity_type: str) -> [str]:
        pass


class ArrayDoc(DocBase):

    def __init__(self, text: str, tokens: [str]):
        self.text = text
        self._tokens = tokens

    def tokens(self) -> Iterable[str]:
        return self._tokens

    def lemmas(self) -> Iterable[str]:
        raise NotImplementedError

    def ents(self, entity_type: str) -> Iterable[str]:
        raise NotImplementedError


class SpacyDoc(DocBase):

    def __init__(self, text: str, doc: Doc, model: SpacyModel):
        self.text = text
        self.doc = doc
        self.model = model

    def tokens(self) -> [str]:
        return (t.text for t in self.doc)

    def lemmas(self) -> [str]:
        return (t.lemma_ for t in self.doc)

    def ents(self, entity_type: str):
        for ent in self.doc.ents:
            if self.spacy_entity_name(entity_type) == ent.label_:
                yield (ent.text, ent.start_char, ent.end_char)

    def spacy_entity_name(self, entity_type):
        return self.model.entity_name(entity_type)


class NLPBase(ABC):

    def __init__(self, lang='de'):
        self.lang = lang

    @abstractmethod
    def process(self, text: str) -> DocBase:
        pass


class SpacyNLP(NLPBase):
    nlp = None
    model = None

    def __init__(self, lang='de'):
        super().__init__(lang=lang)

        if lang == 'de':
            self.model = GermanSpacyModel()
        elif lang == 'en':
            self.model = EnglishSpacyModel()
        else:
            raise ValueError('Unsupported language {}'.format(lang))

        self.nlp = self.model.load()

    def process(self, text: str) -> DocBase:
        doc = self.nlp(text)
        return SpacyDoc(text, doc, self.model)


class NltkNLP(NLPBase):

    def __init__(self, lang='en'):
        super().__init__(lang=lang)
        # TODO load model for given language

    def process(self, text: str) -> DocBase:
        tokens = nltk.word_tokenize(text)
        return ArrayDoc(text, tokens)
