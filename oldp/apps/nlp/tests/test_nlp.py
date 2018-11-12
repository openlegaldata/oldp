import spacy

from django.test import TestCase
from oldp.apps.nlp.base import SpacyNLP, NltkNLP, DocContent


class NLPTestCase(TestCase):
    def test_spacy_tokenization(self):
        nlp = SpacyNLP(lang='de')
        text = u'In den USA kostet ein Burger €5, bzw. 5€'
        expected_tokens = ['In', 'den', 'USA', 'kostet', 'ein', 'Burger', '€', '5', ',', 'bzw.',
                           '5', '€']
        container = nlp.process(text)
        self.assertEqual(expected_tokens, list(container.get_tokens()))

    def test_nltk_tokenization(self):
        nlp = NltkNLP(lang='en')
        text = u'In the U.K. Fish \'n Chips costs £10'
        expected_tokens = ['In', 'the', 'U.K', '.', 'Fish', "'n", 'Chips', 'costs', '£10']
        container = nlp.process(text)
        self.assertEqual(expected_tokens, container.get_tokens())

    def test_spacy_lemmatication(self):
        nlp = SpacyNLP(lang='de')
        text = u'In den USA kostet ein Burger €5, bzw. 5€'
        expected_lemmas = ['In', 'der', 'USA', 'kosten', 'einen', 'Burger', '€', '5', ',',
                           'beziehungsweise', '5', '€']
        container = nlp.process(text)
        self.assertEqual(expected_lemmas, list(container.get_lemmas()))

    def test_spacy_entities(self):
        nlp = SpacyNLP(lang='de')  # in de: ORG, PER, LOC, MISC
        text = 'Die Firma Ferrero, gegründet von Pietro Ferrero, hat ihren Hauptsitz in Alba, ' \
               'Italien'
        expected_ents = [('Ferrero', 10, 17, 'ORG'),
                         ('Pietro Ferrero', 33, 47, 'PER'),
                         ('Alba', 72, 76, 'LOC'),
                         ('Italien', 78, 85, 'LOC')]
        container = nlp.process(text)
        self.assertEqual(expected_ents, container.get_ents())

    def test_doc_container_add_ents(self):
        text = 'a b'
        ents = [('a', 0, 1, 'LETTER'),
                ('b', 2, 3, 'LETTER')]
        nlp = spacy.load('de')
        doc = nlp(text)
        container = DocContent(text, doc)
        container.add_ents(ents)
        self.assertEqual(ents, container.get_ents())
