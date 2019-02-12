from django.test import TestCase

from oldp.apps.cases.models import Case
from oldp.apps.nlp.models import Entity
from oldp.apps.processing.processing_steps.extract_entities import EntityProcessor


class EntityProcessorTestCase(TestCase):
    fixtures = [
        'locations/countries.json',
        'locations/states.json',
        'locations/cities.json',
        'courts/courts.json',
        'cases/cases.json',
        'cases/case_with_references.json',
    ]

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
        entities = [537.52, 347, 190.52, 347, 193.19]
        positions = [(410, 421), (438, 446), (490, 501), (813, 821), (856, 867)]
        case = Case.objects.get(pk=1)

        processor = EntityProcessor()
        processor.entity_types = [Entity.MONEY]
        processor.extract_and_load(case_content, case, lang='de')

        for i, entity in enumerate(case.nlp_entities.all()):
            self.assertEqual(entity.value_float, entities[i])
            self.assertEqual((entity.pos_start, entity.pos_end), positions[i])

    def test_html_content(self):
        case = Case.objects.get(pk=1888)

        processor = EntityProcessor()
        processor.entity_types = [Entity.MONEY, Entity.ORGANIZATION, Entity.LOCATION, Entity.PERSON]
        processor.extract_and_load(case.content, case, lang='de')

        self.assertGreater(case.nlp_entities.all().count(), 50)
