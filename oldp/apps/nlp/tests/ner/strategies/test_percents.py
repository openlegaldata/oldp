from decimal import Decimal

from oldp.apps.nlp.ner.strategies.percents import normalize_percentage_value, \
    GermanPercentageExtractionStrategy
from oldp.apps.nlp.tests.ner.strategies.base import BaseTestCase


class GermanPercentageExtractionStrategyTestCase(BaseTestCase.Strategy):
    strategy = GermanPercentageExtractionStrategy()
    lang = 'de'
    case_content = 'Dies ist ein Beispiel für Prozent- und Promillewerte: 1% = 10 Promille, 99,' \
                   '5 Prozent von 100€ entsprechen 99,5€. Die Promillegrenze liegt bei 0,0 ‰.'
    raw_matches = ['1%', '10 Promille', '99,5 Prozent', '0,0 ‰']
    values = [Decimal('0.01'), Decimal('0.01'), Decimal('0.995'), Decimal('0')]

    def test_regexp(self):
        self.assert_equal_regexp_matches(self.strategy.regex_obj(), self.case_content,
                                         self.raw_matches)

    def test_extract_amounts_from_case(self):
        ents = self.extract_entities(self.strategy, self.case_content, self.lang)
        self.assert_equal_entity_values(ents, self.values)

    def test_percentage_value_normalization(self):
        self.assertEqual(Decimal('0.1'), normalize_percentage_value('0,10'))
        self.assertEqual(Decimal('100'), normalize_percentage_value('100'))
        self.assertEqual(Decimal('100'), normalize_percentage_value('100.0'))
        self.assertEqual(Decimal('100'), normalize_percentage_value('100,0'))
