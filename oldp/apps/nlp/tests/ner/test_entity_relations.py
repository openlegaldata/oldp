from django.test import TestCase
from unittest import skip

import spacy

from oldp.apps.nlp.ner.entity_relations import extract_relations


class EntityRelationsTestCase(TestCase):

    @skip
    def test_extract_pobj_en(self):
        text = 'The man resides in the USA.'
        nlp = spacy.load('en_core_web_sm')
        doc = nlp(text)
        expected_relations = [(('man', 'reside'), ('USA', 23, 25))]
        relations = extract_relations(doc, 'GPE', 'en_core_web_sm')
        self.assertEqual(expected_relations, list(relations))

    @skip
    def test_extract_dobj_en(self):
        text = 'The cat owns 1000 €.'
        nlp = spacy.load('en_core_web_sm')
        doc = nlp(text)
        expected_relations = [(('cat', 'own'), ('1000 €', 13, 18))]
        relations = extract_relations(doc, 'MONEY', 'en_core_web_sm')
        self.assertEqual(expected_relations, list(relations))

    def test_extract_relations_oa_de(self):
        text = 'Der Hund begrüßt Anton.'
        nlp = spacy.load('de_core_news_sm')
        doc = nlp(text)
        expected_relations = [(('Hund', 'begrüßen'), ('Anton', 17, 21))]
        relations = extract_relations(doc, 'PER', 'de_core_news_sm')
        self.assertEqual(expected_relations, list(relations))

    def test_extract_relations_nk_de(self):
        text = 'Der Vogel fliegt verbringt den Winter in Afrika.'
        nlp = spacy.load('de_core_news_sm')
        doc = nlp(text)
        expected_relations = [(('Vogel', 'in'), ('Afrika', 41, 46))]
        relations = extract_relations(doc, 'LOC', 'de_core_news_sm')
        self.assertEqual(expected_relations, list(relations))
