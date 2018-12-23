from abc import ABC, abstractmethod

import nltk
from spacy.tokens import Doc

from oldp.apps.nlp.language_models import GermanSpacyModel, SpacyModel


class DocBase(ABC):

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
    def get_ents(self, entity_type: str) -> [str]:
        pass


class ArrayDoc(DocBase):

    def __init__(self, text: str, tokens: [str]):
        self.text = text
        self.tokens = tokens

    def get_text(self) -> [str]:
        return self.text

    def get_tokens(self) -> [str]:
        return self.tokens

    def get_lemmas(self) -> [str]:
        raise NotImplementedError

    def get_ents(self, entity_type: str) -> [str]:
        raise NotImplementedError


class SpacyDoc(DocBase):

    def __init__(self, text: str, doc: Doc, model: SpacyModel):
        self.text = text
        self.doc = doc
        self.model = model
        self.ents = []

    def get_text(self) -> [str]:
        return self.text

    def get_tokens(self) -> [str]:
        return [t.text for t in self.doc]

    def get_lemmas(self) -> [str]:
        return [t.lemma_ for t in self.doc]

    def get_ents(self, entity_type: str):
        for ent in self.doc.ents:
            if self.model.get_entity_name(entity_type) == ent.label_:
                yield (ent.text, ent.start_char, ent.end_char)


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
