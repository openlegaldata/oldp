from abc import ABC, abstractmethod

import nltk
import spacy
from spacy.tokens import Doc


class Content(ABC):

    @abstractmethod
    def get_text(self) -> [str]:
        pass

    @abstractmethod
    def get_tokens(self) -> [str]:
        pass

    @abstractmethod
    def get_lemmas(self) -> [str]:
        pass

    @abstractmethod
    def get_ents(self) -> [str]:
        pass


class ArrayContent(Content):

    def __init__(self, text: str, tokens: [str]):
        self.text = text
        self.tokens = tokens

    def get_text(self) -> [str]:
        return self.text

    def get_tokens(self) -> [str]:
        return self.tokens

    def get_lemmas(self) -> [str]:
        raise NotImplementedError

    def get_ents(self) -> [str]:
        raise NotImplementedError


class DocContent(Content):

    def __init__(self, text: str, doc: Doc):
        self.text = text
        self.doc = doc
        self.ents = []

    def get_text(self) -> [str]:
        return self.text

    def get_tokens(self) -> [str]:
        return [t.text for t in self.doc]

    def get_lemmas(self) -> [str]:
        return [t.lemma_ for t in self.doc]

    def add_ents(self, ents):
        self.ents += ents

    def get_ents(self):
        return self.ents + \
            [(ent.text, ent.start_char, ent.end_char, ent.label_) for ent in self.doc.ents]


class NLPBase(ABC):

    def __init__(self, lang='de'):
        if lang not in self.installed_languages:
            raise ValueError('Unsupported language {}'.format(lang))
        self.lang = lang

    @abstractmethod
    def process(self, text: str) -> Content:
        pass

    @property
    @abstractmethod
    def installed_languages(self):
        pass


class SpacyNLP(NLPBase):
    installed_languages = ['de']

    def __init__(self, lang='de'):
        super().__init__(lang=lang)
        self.nlp = spacy.load(self.lang)

    def process(self, text: str) -> Content:
        doc = self.nlp(text)
        return DocContent(text, doc)


class NltkNLP(NLPBase):
    installed_languages = ['en']

    def __init__(self, lang='en'):
        super().__init__(lang=lang)

    def process(self, text: str) -> Content:
        tokens = nltk.word_tokenize(text)
        return ArrayContent(text, tokens)
