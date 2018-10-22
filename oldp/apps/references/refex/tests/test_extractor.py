from unittest import TestCase

from oldp.apps.references.refex.extractor import RefExtractor


class RefExTest(TestCase):
    def setUp(self):
        pass

    def tearDown(self):
        pass

    def test_extract(self):
        """
        § 3d AsylG
        § 123 VwGO
        §§ 3, 3b AsylG
        § 77 Abs. 1 Satz 1, 1. Halbsatz AsylG
        § 3 Abs. 1 AsylG
        § 77 Abs. 2 AsylG
        § 113 Abs. 5 Satz 1 VwGO
        § 3 Abs. 1 Nr. 1 i.V.m. § 3b AsylG
        § 3a Abs. 1 und 2 AsylG
        §§ 154 Abs. 1 VwGO
        § 83 b AsylG
        § 167 VwGO iVm §§ 708 Nr. 11, 711 ZPO
        § 167 VwGO i.V.m. §§ 708 Nr. 11, 711 ZPO
        §§ 167 Abs. 2 VwGO, 708 Nr. 11, 711 ZPO
        §§ 52 Abs. 1; 53 Abs. 2 Nr. 1; 63 Abs. 2 GKG
        § 6 Abs. 5 Satz 1 LBO
        §§ 80 a Abs. 3, 80 Abs. 5 VwGO
        § 1 Satz 2 SbStG
        § 2 ZWStS
        § 6 Abs. 2 S. 2 ZWStS

        :return:
        """
        content_html = '<h1>Hallo</h1><p>Ein Satz mit § 3 Abs. 1 Nr. 1 i.V.m. § 3b AsylG, und weiteren Sachen.</p>'

        x = RefExtractor()
        x.do_law_refs = True
        x.do_case_refs = False
        new_content, markers = x.extract(content_html)

        print(new_content)
        print('Markers: %s' % markers)
