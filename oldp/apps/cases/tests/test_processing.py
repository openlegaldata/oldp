import logging
import os
import re
from unittest import skip

from django.test import TestCase

from oldp.apps.cases.models import Case
from oldp.apps.cases.processing.processing_steps.extract_refs import ExtractRefs
from oldp.apps.references.models import CaseReferenceMarker
from oldp.utils.test_utils import TestCaseHelper

# from oldp.apps.backend.tests import TestCaseHelper

logger = logging.getLogger(__name__)
RESOURCE_DIR = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'resources')


class CaseProcessingTest(TestCase, TestCaseHelper):
    fixtures = ['courts.json']

    @skip  # TODO write with django serializer
    def test_extract_law_refs_1(self):
        unprocessed = Case.from_json_file(os.path.join(RESOURCE_DIR, 'extract_refs/1.json'))
        case = ExtractRefs(law_refs=True, case_refs=False).process(unprocessed)

        # TODO Validate test - old value: 33
        self.assertEqual(33, len(case.reference_markers), 'Invalid number of references')

    @skip  # TODO write with django serializer
    def test_extract_law_refs_2(self):
        unprocessed = Case.from_json_file(os.path.join(RESOURCE_DIR, 'extract_refs/2.json'))
        case = ExtractRefs(law_refs=True, case_refs=False).process(unprocessed)

        # TODO Validate test - old value: 42
        self.assertEqual(42, len(case.reference_markers), 'Invalid number of references')

    @skip
    def test_extract_law_and_case_refs_3(self):  # TODO Requires more law book BauGB
        """
        Assert:

        (vgl. Schl.-Holst. OVG, Urteil vom 19.01.2012 - 1 LB 11/11 -, juris [Rn. 23 f.])
        (vgl. OVG NRW, Urteil vom 10.10.1996 - 7 A 4185/95 -, juris [Rn. 68])
        (vgl. BVerwG, Beschluss vom 12.11.1987 - 4 B 216/87 -, juris [Rn. 2]; VGH BW, Urteil vom 10.01.2007 - 3 S 1251/06 -, juris [Rn. 25])
        (so BVerfG in std. Rspr., vgl. z.B. BVerfG, Beschluss vom 23.07.2003 –- 2 BvR 624/01 -, juris [Rn. 16 f.])

        :return:
        """
        unprocessed = Case.from_json_file(os.path.join(RESOURCE_DIR, 'extract_refs/3.json'))
        case = ExtractRefs(law_refs=True, case_refs=True).process(unprocessed)

        self.assertEqual(5, len(case.reference_markers), 'Invalid number of references')

    @skip  # TODO write with django serializer
    def test_extract_case_refs_from_juris(self):
        fixtures = [
            {
                'file': '1.json',
                'ref_count': 8,  # TODO verify number
            },
            {
                'file': '2.json',
                'ref_count': 5,  # TODO verify number
            },
            {
                'file': '3.json',
                'ref_count': 5,  # Correct number
            }
        ]

        for f in fixtures:
            unprocessed = Case.from_json_file(os.path.join(RESOURCE_DIR, 'extract_refs/juris/' + f['file']))
            case = ExtractRefs(law_refs=False, case_refs=True).process(unprocessed)

            self.assertEqual(f['ref_count'], len(case.reference_markers), 'Invalid number of references: %s' % f)

    @skip  # TODO write with django serializer
    def test_extract_case_refs(self):
        unprocessed = Case.from_json_file(os.path.join(RESOURCE_DIR, 'extract_refs/2.json'))
        case = ExtractRefs(law_refs=False, case_refs=True).process(unprocessed)

        # TODO Old validated value: 14
        self.assertEqual(20, len(case.reference_markers), 'Invalid number of references')

    @skip  # TODO write with django serializer
    def test_extract_law_and_case_refs_2(self):
        unprocessed = Case.from_json_file(os.path.join(RESOURCE_DIR, 'extract_refs/2.json'))
        case = ExtractRefs(law_refs=True, case_refs=True).process(unprocessed)

        # TODO Old validated value: 56
        self.assertEqual(62, len(case.reference_markers), 'Invalid number of references')

    def test_regex_file_numbers(self):
        text = '(vgl. Schl.-Holst. OVG, Urteil vom 19.01.2012 - 1 LB 11/11 -, juris [Rn. 23 f.])'
        text += '(vgl. OVG NRW, Urteil vom 10.10.1996 - 7 A 4185/95 -, juris [Rn. 68])'
        text += '(vgl. BVerwG, Beschluss vom 12.11.1987 - 4 B 216/87 -, juris [Rn. 2]; VGH BW, Urteil vom 10.01.2007 - 3 S 1251/06 -, juris [Rn. 25])'
        text += '(so BVerfG in std. Rspr., vgl. z.B. BVerfG, Beschluss vom 23.07.2003 –- 2 BvR 624/01 -, juris [Rn. 16 f.])'
        text += ' (vgl. OVG Berlin-Brbg., Urt. v. 17.07.2014 - OVG 7 B 40.13 -, Juris Rn. 35;)'  # TODO file number format

        expected = ['1 LB 11/11', '7 A 4185/95', '4 B 216/87', '3 S 1251/06', '2 BvR 624/01']
        actual = []

        fns_matches = list(re.finditer(ExtractRefs().get_file_number_regex(), text))

        for f in fns_matches:
            actual.append(f.group())

        self.assert_items_equal(expected, actual, 'Invalid file numbers extracted')

    def test_regex_court_names(self):
        text = '(vgl. Schl.-Holst. OVG, Urteil vom 19.01.2012 - 1 LB 11/11 -, juris [Rn. 23 f.])'
        text += '(vgl. OVG NRW, Urteil vom 10.10.1996 - 7 A 4185/95 -, juris [Rn. 68])'
        text += '(vgl. BVerwG, Beschluss vom 12.11.1987 - 4 B 216/87 -, juris [Rn. 2]; VGH BW, Urteil vom 10.01.2007 - 3 S 1251/06 -, juris [Rn. 25])'
        text += '(so BVerfG in std. Rspr., vgl. z.B. BVerfG, Beschluss vom 23.07.2003 –- 2 BvR 624/01 -, juris [Rn. 16 f.])'

        expected = ['Schl.-Holst. OVG', 'OVG NRW', 'BVerwG', 'VGH BW', 'BVerfG', 'BVerfG']
        actual = []

        fns_matches = list(re.finditer(ExtractRefs().get_court_name_regex(), text))

        for f in fns_matches:
            actual.append(f.group())

        self.assert_items_equal(expected, actual, 'Invalid court names extracted', debug=True)



    def test_clean_text(self):
        text = 'Obgleich die Baulast ein Institut des in die Kompetenz des Landesgesetzgebers fallenden bauaufsic' \
               'htlichen Verfahrens ist, der deshalb auch die formellen und materiellen Voraussetzungen ihres Ent' \
               'stehens und Erlöschens bestimmt, darf sich die übernommene Belastung auch auf die Nutzung des Gru' \
               'ndstücks in bodenrechtlicher (bebauungsrechtlicher) Hinsicht beziehen (vgl. BVerwG, Beschluss vom' \
               ' 12.11.1987 - 4 B 216/87 -, juris [Rn. 2]; VGH BW, Urteil vom 10.01.2007 - 3 S 1251/06 -, juris' \
               ' [Rn. 25]).'

        # print('BEFORE = %s' % text)
        # print()
        # print(self.indexer.clean_text_for_tokenizer(text))
        #
        self.assertEqual('Obgleich die Baulast ein Institut des in die Kompetenz des Landesgesetzgebers fallenden '
                         'bauaufsichtlichen Verfahrens ist, der deshalb auch die formellen und materiellen Voraus'
                         'setzungen ihres Entstehens und Erlöschens bestimmt, darf sich die übernommene Belastung'
                         ' auch auf die Nutzung des Grundstücks in bodenrechtlicher ______________________ Hinsic'
                         'ht beziehen ____________________________________________________________________________________________________________________________________.', ExtractRefs().clean_text_for_tokenizer(text))


    def test_handle_multiple_law_refs(self):
        ref_str = '§§ 10000 Abs. 3 ZPO, 151, 153 VwGO'
        law_ids = ExtractRefs().handle_multiple_law_refs(ref_str, [])

        self.assertEqual([{'sect': '153', 'book': 'vwgo', 'type': 'law'}, {'sect': '151', 'book': 'vwgo', 'type': 'law'}, {'sect': '10000', 'book': 'zpo', 'type': 'law'}], law_ids)
        # print(law_ids)


    def test_extract_law_refs_detailed(self):

        expected = [
            {
                'content': 'Die Zulassung der Berufung folgt aus §§ 124 Abs. 2 Nr. 3, 124 a Abs. 1 Satz 1 VwGO wegen grundsätzlicher Bedeutung.',
                'refs': [
                    {'book': 'vwgo', 'sect': '124a', 'type': 'law'},
                    {'book': 'vwgo', 'sect': '124', 'type': 'law'}
                ]
            },
            {
                'content': 'Die Entscheidung über die vorläufige Vollstreckbarkeit folgt '
                           'aus § 167 VwGO i.V.m. §§ 708 Nr. 11, 711 ZPO.',
                'refs': [
                    # '§ 167 VwGO',
                    # '§§ 708 Nr. 11, 711 ZPO'
                    {'book': 'vwgo', 'sect': '167', 'type': 'law'},
                    {'book': 'zpo', 'sect': '711', 'type': 'law'},
                    {'book': 'zpo', 'sect': '708', 'type': 'law'}
                ]
            },
            {
                'content': 'Die Kostenentscheidung beruht auf § 154 Abs. 1 VwGO. Die außergerichtlichen Kosten des '
                           'beigeladenen Ministeriums waren für erstattungsfähig zu erklären, da dieses einen '
                           'Sachantrag gestellt hat und damit ein Kostenrisiko eingegangen ist '
                           '(vgl. §§ 162 Abs. 3 ZPO, 151, 153 VwGO).',
                'refs': [
                    {'book': 'vwgo', 'sect': '154', 'type': 'law'},
                    {'book': 'vwgo', 'sect': '153', 'type': 'law'},
                    {'book': 'vwgo', 'sect': '151', 'type': 'law'},
                    {'book': 'zpo', 'sect': '162', 'type': 'law'}
                ]
            },
            {
                'content': 'Dies gilt grundsätzlich für die planerisch ausgewiesenen und die faktischen '
                           '(§ 34 Abs. 2 BauGB) Baugebiete nach §§ 2 bis 4 BauNVO, die Ergebnis eines typisierenden '
                           'Ausgleichs möglicher Nutzungskonflikte sind. Setzt die Gemeinde einen entsprechenden Gebietstyp fest',
                'refs': [
                    {'book': 'baugb', 'sect': '34', 'type': 'law'},
                    {'book': 'baunvo', 'sect': '4', 'type': 'law'},
                    {'book': 'baunvo', 'sect': 3, 'type': 'law'},
                    {'book': 'baunvo', 'sect': '2', 'type': 'law'}
                ]
            },
            {
                'content': 'Die Kostenentscheidung beruht auf § 154 Abs. 1 VwGO. Die außergerichtlichen Kosten des'
                           ' beigeladenen Ministeriums waren für erstattungsfähig zu erklären, da dieses einen '
                           'Sachantrag gestellt hat und damit ein Kostenrisiko eingegangen ist '
                           '(vgl. §§ 162 Abs. 3, 154 Abs. 3 VwGO).',
                # 'content': 'Die Kostenentscheidung beruht auf § 154 Abs. 1 VwGO. ',
                # 'content': '(vgl. §§ 162 Abs. 3, 154 Abs. 3 VwGO).',
                'refs': [ # TODO main regex not working for §§ 162 Abs. 3, 154 Abs. 3 VwG
                    {'book': 'vwgo', 'sect': '154', 'type': 'law'},
                    {'book': 'vwgo', 'sect': '154', 'type': 'law'},
                    {'book': 'vwgo', 'sect': '162', 'type': 'law'}
                ]
            },
            {
                'content': '2. Der Klagantrag zu 2. ist unzulässig. Es handelt sich um einen Anfechtungsantrag '
                           'nach § 42 Abs. 1 Alt. 1 VwGO bezüglich der seitens des beigeladenen Ministeriums '
                           'getroffenen ergänzenden Abweichungsentscheidung vom 13.05.2016 in Gestalt des'
                           ' Widerspruchsbescheides vom 14.08.2016.',
                'refs': [
                    {'book': 'vwgo', 'sect': '42', 'type': 'law'}
                ]
            }
        ]

        self.assert_refs(expected)

    def test_timeout_ref(self):
        expected = [
            {
                'content': ' Auslandsaufenthalt mit beachtlicher Wahrscheinlichkeit aufgrund eines ihm (zugeschriebenen) Verfolgungsgrundes '
                           'im Sinne des § 3 Abs. 1 AsylG, insbesondere einer regimekritischen politischen Überzeugung, erfolgen würden. '
                           'Nach der Rechtsprechung des schleswig-holsteinischen Oberverwaltungsgerichtes (Urteil vom 23.11.2016, - 3 LB 17/16 -, juris), '
                           'der sich die Kammer anschließt, besteht nach der gegenwärtigen Erkenntnislage keine hinreichende'
                           ' Grundlage für die Annahme, dass der totalitäre syrische Staat jeden Rückkehrer pauschal unter eine '
                           'Art Generalsverdacht stellt, der Opposition anzugehören (so auch OVG Saarland, '
                           'Urteil vom 2.2.2017, - 2 A 515/16 -; OVG Rheinland-Pfalz, Urteil vom 16.12.2016, -1A 10922/16 -; Bayrischer VGH, '
                           'Urteil vom 12.12.16, - 21 B 16.30364; OVG Nordrhein-Westfalen,',
                'refs': [
                    {'book': 'asylg', 'sect': '3', 'type': 'law'}
                ]
            }
        ]

        self.assert_refs(expected)

    def test_extract_case_refs_detail(self):
        fixtures = [

            {
                'content': 'Rückwirkend zum 01.01.2014 trat das Gesetz zur Neufassung des Landesplanungsgesetzes (LaplaG) und zur Aufhebung '
                           'des Landesentwicklungsgrundsätzegesetzes'
                           ' vom 27.01.2014 (GVOBl. 12). Das OVG Schleswig habe bereits in seinem Urteil vom 22.04.2010 (1 KN 19/09) zur '
                           'im Wesentlichen gleichlautenden Vorgängervorschrift im LROP-TF 2004 festgestellt, dass dieser Vorschrift die'
                           ' erforderliche Bestimmtheit bzw. Bestimmbarkeit und damit die Zielqualität nicht zukomme.',
                'refs': [
                    {'ecli': 'ecli://de/ovg-schleswig/1-kn-19-09', 'type': 'case'}
                ]
            }
        ]

        self.assert_refs(fixtures, law_refs=False, case_refs=True)

    def assert_refs(self, expected, law_refs=True, case_refs=False):
        case = Case()

        for i, test in enumerate(expected):

            if law_refs:
                content, refs = ExtractRefs().extract_law_refs(referenced_by=case,
                                                               content=test['content'])
            elif case_refs:
                content, refs = ExtractRefs().extract_case_refs(referenced_by=case,
                                                                content=test['content'])
            else:
                raise ValueError('Foooo')

            ref_ids = []
            for ref in refs:  # type: CaseReferenceMarker
                ref_ids.extend(ref.get_references())

            # print('-----')

            logger.debug('actual: %s' % ref_ids)
            logger.debug('expected: %s' % test['refs'])

            self.assertListEqual(ref_ids, test['refs'], 'Invalid ids returned (test #%i)' % i)

    def test_extract_refs(self):
        pass

    def test_assign_courts(self):
        pass

    def test_assign_topics(self):
        pass
