from django.test import TestCase

from oldp.apps.nlp.base import SpacyNLP


class BaseTestCase:
    class Strategy(TestCase):

        def extract_entities(self, strategy, string, lang):
            nlp = SpacyNLP(lang=lang)
            doc = nlp.process(string)
            return strategy.extract(doc)

        def assert_equal_regexp_matches(self, regexp, string, expected_matches):
            for i, match in enumerate(regexp.finditer(string)):
                self.assertEqual(expected_matches[i], match.group(0))

        def assert_equal_entity_values(self, entities, expected_values):
            for i, (value, start, end) in enumerate(entities):
                self.assertEqual(expected_values[i], value)

    class RegEx(TestCase):
        def assert_match_all(self, strings, r):
            for string in strings:
                self.assertTrue(r.match(string))

        def assert_match_none(self, strings, r):
            for string in strings:
                self.assertFalse(r.match(string))
