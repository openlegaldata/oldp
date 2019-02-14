from django.test import TestCase

from oldp.apps.nlp.lemmatizer import lemmatize


class LemmatizerTestCase(TestCase):

    def test_lemmatize_noun(self):
        self.assertEqual('Katze', lemmatize('Katzen', lang='de'))

    def test_lemmatize_verb(self):
        self.assertEqual('leben', lemmatize('lebte', lang='de'))
