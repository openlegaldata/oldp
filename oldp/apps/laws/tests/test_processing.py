# -*- coding: utf-8 -*-
import os
from typing import List
from unittest import skip

from django.test import TestCase, tag

from oldp.apps.laws.models import Law
from oldp.apps.laws.processing.law_processor import LawProcessor, LawInputHandlerFS
from oldp.apps.laws.processing.processing_steps.extract_refs import ProcessingStep as ExtractRefsStep

RESOURCE_DIR = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'resources')


@tag('processing')
class LawsProcessingTestCase(TestCase):
    fixtures = ['laws/laws.json']

    def __init__(self, *args, **kwargs):
        super(LawsProcessingTestCase, self).__init__(*args, **kwargs)

    def setUp(self):
        pass

    def tearDown(self):
        # os.remove(self.temp_path)
        pass

    @skip
    def test_extract_refs(self):
        # TODO currently not working
        content = Law.objects.get(book__slug='ublg-1', slug='12')
        # print(content)
        # print(content.get_reference_markers())

        step = ExtractRefsStep()
        processed = step.process(content)

        # print(processed)
        # print(processed.reference_markers)

        self.assertEqual(len(processed.get_reference_markers()), 1, 'Invalid number of reference markers')
        # self.assertEqual(processed.get_reference_markers()[0].referenced_by, content, 'Invalid reference markers by')
        # self.assertEqual(processed.get_reference_markers()[0].start, 764, 'Invalid reference markers start')
        # self.assertEqual(processed.get_reference_markers()[0].end, 767, 'Invalid reference markers end')

    @skip
    def test_extract_refs_detail(self):
        # TODO currently not working
        text = '<P>Anforderungsbeh&#246;rden gem&#228;&#223; § 5 Abs. 1 und § 79 Satz 1 des Bundesleistungs' \
               'gesetzes sind, soweit in §§ 2 bis 4 nichts anderes bestimmt ist, die Beh&#246;rden der allgemeinen ' \
               'Verwaltung auf der Kreisstufe.</P>'

        law = Law.objects.get(book__slug='ublg-1', slug='12')
        law_processed = ExtractRefsStep().process(law)

        # print('Original: %s' % text)
        # print('\nMarker: %s' % ref_text)

        # self.assertEqual(len(law_processed.get_references()), 3, 'Invalid number of reference markers')

        # TODO Reference count?

        # print(refs)

    def test_empty_content(self):
        processor = LawProcessor()
        law_books, laws, markers = processor.empty_content()

        deleted_rows, info = law_books  # Contains other types from foreign keys as well

        self.assertEqual(123, deleted_rows, 'Invalid number of rows deleted')

    def test_law_input_handler_fs(self):
        ih = LawInputHandlerFS(limit=10, selector=os.path.join(RESOURCE_DIR, 'from_bundesgit'))
        ih.pre_processed_content = []
        # test get_input
        self.assertEqual(2, len(ih.get_input()), 'Invalid number of input files')

        # test handle_input
        ih.handle_input(os.path.join(RESOURCE_DIR, 'from_bundesgit', 's', 'stvo_2013', 'stvo_2013.xml'))
        items = ih.pre_processed_content  # type: List[Law]

        self.assertEqual(61, len(items), 'Invalid count')
        self.assertEqual('Grundregeln', items[0].title, 'Invalid title')
        self.assertEqual('1', items[0].slug, 'Invalid slug')
        self.assertEqual('Straßenverkehrs-Ordnung', items[0].book.title, 'Invalid book title')

        ih.pre_processed_content = []
        ih.handle_input(os.path.join(RESOURCE_DIR, 'from_bundesgit', 'b', 'baunvo', 'baunvo.xml'))
        items = ih.pre_processed_content  # type: List[Law]

        self.assertEqual(35, len(items), 'Invalid count')
        self.assertEqual('Reine Wohngebiete', items[3].title, 'Invalid title')
        self.assertEqual('3', items[3].slug, 'Invalid slug')
        self.assertEqual('Verordnung über die bauliche Nutzung der Grundstücke', items[3].book.title, 'Invalid book title')

        # print(items)
