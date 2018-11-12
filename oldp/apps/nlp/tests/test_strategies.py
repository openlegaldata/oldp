from django.test import TestCase

from oldp.apps.nlp.base import SpacyNLP
from oldp.apps.nlp.ner_strategies import UniversalMoneyExtractionStrategy


class BaseTestCase:
    class Strategy(TestCase):
        def assert_match_all(self, strategy, string, matches):
            nlp = SpacyNLP()
            content = nlp.process(string)
            for i, (value, start, end) in enumerate(strategy.extract(content)):
                self.assertEqual(matches[i], value)


class UniversalMoneyExtractionStrategyTestCase(BaseTestCase.Strategy):
    strategy = UniversalMoneyExtractionStrategy

    def test_extract_euros_from_case(self):
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
        euros = ['537,52 Euro', '347 Euro', '190,52 Euro', '347 Euro', '193,19 Euro']
        self.assert_match_all(self.strategy(lang='de'),
                              case_content,
                              euros)
