from django.test import TestCase

from oldp.apps.nlp.models import NLPContent
from oldp.apps.processing.processing_steps.extract_entities import get_text_from_html, \
    EntityProcessor


class EntityProcessorTestCase(TestCase):

    def test_extract_and_load(self):
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
        nlp_content = NLPContent()
        nlp_content.save()

        processor = EntityProcessor()
        processor.entity_types = ['money']
        processor.extract_and_load(get_text_from_html(case_content), nlp_content, lang='de')

        for i, entity in enumerate(nlp_content.entity_set.all()):
            self.assertEqual(entity.value, euros[i])


class HtmlCleaning(TestCase):

    def test_get_text_from_html(self):
        case_content = "<h2>Tenor</h2>\n\n<div>\n         <dl class=\"RspDL\">\n       <dt/>\n   " \
                       "         <dd>\n               <p>Auf die Revision des Beklagten wird das " \
                       "Urteil des ... " \
                       "in der Fassung des Erg&#228;nzungsurteils ... zum Nachteil des Beklagten " \
                       "entschieden worden ist.</p>\n            </dd>\n         </dl>       <dl " \
                       "class=\"RspDL\">\n            <dt/>\n            <dd>\n          <p/>\n  " \
                       "          </dd>\n         </dl>\n         <dl class=\"RspDL\">\n         " \
                       "<dt/>\n            <dd>\n            <p>Im Umfang der Aufhebung wird die " \
                       "Berufung ... zur&#252;ckgewiesen. Die weitergehende " \
                       "Berufung bleibt zur&#252;ckgewiesen.</p>\n         </dd>\n         </dl>\n "
        self.assertEqual(u'Tenor Auf die Revision des Beklagten wird das Urteil des ... in der '
                         u'Fassung des Ergänzungsurteils ... zum Nachteil des Beklagten '
                         u'entschieden worden ist. Im Umfang der Aufhebung wird die Berufung ... '
                         u'zurückgewiesen. Die weitergehende Berufung bleibt zurückgewiesen. ',
                         get_text_from_html(case_content))
