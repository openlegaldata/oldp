from unittest import skip

from django.test import TestCase

from oldp.apps.nlp.base import SpacyNLP, NltkNLP
from oldp.apps.nlp.models import Entity


@skip
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
        container = nlp.process(text)
        self.assertEqual([('Alba', 72, 76),
                         ('Italien', 78, 85)],
                         list(container.get_ents(Entity.LOCATION)))
        self.assertEqual([('Ferrero', 10, 17)],
                         list(container.get_ents(Entity.ORGANIZATION)))
        self.assertEqual([('Pietro Ferrero', 33, 47)],
                         list(container.get_ents(Entity.PERSON)))
