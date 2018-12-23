from decimal import Decimal

from oldp.apps.nlp.ner.strategies.money import GermanCurrencyExtractionStrategy, \
    GermanEuroExtractionStrategy, normalize_money_amount
from oldp.apps.nlp.tests.ner.strategies.base import BaseTestCase


class MoneyExtractionStrategyTestCase(BaseTestCase.Strategy):

    def test_money_amount_normalization(self):
        self.assertEqual(Decimal('0.1'), normalize_money_amount('0,10'))
        self.assertEqual(Decimal('6666.66'), normalize_money_amount('6.666,66'))
        self.assertEqual(Decimal('42'), normalize_money_amount('42,00'))
        self.assertEqual(Decimal('42'), normalize_money_amount('42'))


class GermanEuroExtractionStrategyTestCase(BaseTestCase.Strategy, BaseTestCase.RegEx):
    strategy = GermanEuroExtractionStrategy()
    lang = 'de'
    case_content = 'Der Kläger lebte bis Ende 2006 in B., zog dann nach Ba. um und Anfang ' \
                   '2008 nach B. zurück. Er bezog bereits bei seinem ersten B.- Aufenthalt ' \
                   'Leistungen der Grundsicherung für Arbeitsuchende nach dem SGB II. Der in ' \
                   'B. für ihn zuständige Grundsicherungsträger, die Arge E., gewährte ihm ' \
                   'bis Dezember 2007 Leistungen zur Sicherung des Lebensunterhalts - ohne ' \
                   'sanktionsbedingten oder sonstigen Abzug - in Höhe von 537,52 Euro (' \
                   'Regelleistung: 347 Euro und Leistungen für Unterkunft und Heizung: 190,' \
                   '52 Euro). Durch Bescheid vom 14.1.2008 hob sie die Bewilligung mit ' \
                   'Wirkung ab dem 1.2.2008 wegen des Wechsels der Zuständigkeit auf Grund ' \
                   'des Umzugs des Klägers auf. Am 25.1.2008 bewilligte der Beklagte dem ' \
                   'Kläger für den Zeitraum vom 1.2.2008 bis 30.6.2008 ' \
                   'Grundsicherungsleistungen in Gestalt einer Regelleistung von 347 Euro ' \
                   'und für Kosten der Unterkunft von 193,19 Euro.'
    raw_matches = ['537,52 Euro', '347 Euro', '190,52 Euro', '347 Euro', '193,19 Euro']
    values = [Decimal('537.52'), Decimal('347'), Decimal('190.52'), Decimal('347'),
              Decimal('193.19')]

    def test_euro_amounts(self):
        euros = ['1€', '1000000€', '3.000€', '3.000.000 €', '999,99€', '100 Euro', '1,20Euro']
        self.assert_match_all(euros, self.strategy.regex_obj())

    def test_non_euro_amounts(self):
        not_euros = ['€1', '10$', '30.00€', '100,000€', 'Euro', 'Euro 1000']
        self.assert_match_none(not_euros, self.strategy.regex_obj())

    def test_regexp(self):
        self.assert_equal_regexp_matches(self.strategy.regex_obj(), self.case_content,
                                         self.raw_matches)

    def test_extract_amounts_from_case(self):
        ents = self.extract_entities(self.strategy, self.case_content, self.lang)
        self.assert_equal_entity_values(ents, self.values)


class GermanCurrencyExtractionStrategyTestCase(BaseTestCase.Strategy):
    strategy = GermanCurrencyExtractionStrategy()
    lang = 'de'
    case_content = 'Dieser Text enthält Werte in USD, Britischen Pfund und Euro. Zum 23.12.2018 ' \
                   'sind 1€ ungefähr 0,9 Britische Pfund und 1,14 USD.'
    raw_matches = ['1€', '0,9 Britische Pfund', '1,14 USD']
    values = [('EUR', Decimal('1')), ('GBP', Decimal('0.9')), ('USD', Decimal('1.14'))]

    def test_regexp(self):
        self.assert_equal_regexp_matches(self.strategy.regex_obj(), self.case_content,
                                         self.raw_matches)

    def test_extract_amounts_from_case(self):
        ents = self.extract_entities(self.strategy, self.case_content, self.lang)
        self.assert_equal_entity_values(ents, self.values)

    def test_currency_code_computation(self):
        self.assertEqual('EUR', self.strategy.compute_currency_code('EUR'))
        self.assertEqual('EUR', self.strategy.compute_currency_code('€'))
        self.assertEqual('EUR', self.strategy.compute_currency_code('Euro'))
        self.assertEqual('EUR', self.strategy.compute_currency_code('Euros'))
        self.assertEqual('USD', self.strategy.compute_currency_code('USD'))
        self.assertEqual('USD', self.strategy.compute_currency_code('$'))
        self.assertEqual('USD', self.strategy.compute_currency_code('US-Dollar'))
        self.assertEqual('USD', self.strategy.compute_currency_code('US-Dollars'))
        self.assertEqual('USD', self.strategy.compute_currency_code('Dollar'))
        self.assertRaises(ValueError, self.strategy.compute_currency_code, 'Hallo')
