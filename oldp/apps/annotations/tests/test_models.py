import json
import logging
import os
from unittest import skip

import lxml.html
from django.contrib.auth.models import AnonymousUser, User
from django.core.exceptions import ValidationError
from django.test import TransactionTestCase, tag, RequestFactory
from lxml.cssselect import CSSSelector

from oldp.apps.annotations.models import CaseAnnotation, AnnotationLabel, CaseMarker
from oldp.apps.cases.models import Case

logger = logging.getLogger(__name__)
RESOURCE_DIR = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'resources')


@tag('models')
class AnnotationsModelsTestCase(TransactionTestCase):
    fixtures = [
        'users/with_password_unittest.json',  # password=unittest
        'locations/countries.json',
        'locations/states.json',
        'locations/cities.json',
        'courts/courts.json',
        'cases/cases.json',
        'annotations/labels.json',
    ]

    def setUp(self):
        self.factory = RequestFactory()

    def test_get_annotations(self):
        c = Case.objects.get(pk=1)
        l = AnnotationLabel.objects.get(pk=1)

        CaseAnnotation(label_id=1, belongs_to=c, value_str='fff').save()
        CaseAnnotation(label_id=2, belongs_to=c, value_str='fff').save()

        # Check on validations
        try:
            ca2 = CaseAnnotation(label_id=1, belongs_to=c, value_str='fffxxx')
            ca2.clean()
            raise ValueError('Not raised validation error')
        except ValidationError:
            pass

        anos = c.get_annotations()

        for a in anos:
            print(a)

        self.assertTrue(anos.count(), 2)

    def test_get_annotations_with_request(self):
        c = Case.objects.get(pk=1)

        CaseAnnotation(label_id=1, belongs_to=c, value_str='fff').save()
        CaseAnnotation(label_id=2, belongs_to=c, value_str='fff').save()

        request = self.factory.get(c.get_absolute_url())
        request.user = AnonymousUser()

        guest_annotations = c.get_annotations(request)

        owner_request = self.factory.get(c.get_absolute_url())
        owner_request.user = User.objects.get(pk=1)

        owner_annotations = c.get_annotations(owner_request)

        # One label is private, thus guest should see less annotations
        self.assertEqual(len(guest_annotations), 1)
        self.assertEqual(len(owner_annotations), 2)

    def test_grouped_annotations(self):
        c = Case.objects.get(pk=1)

        CaseAnnotation(label_id=2, belongs_to=c, value_str='foo').save()
        CaseAnnotation(label_id=3, belongs_to=c, value_str='a').save()
        CaseAnnotation(label_id=3, belongs_to=c, value_str='b').save()
        CaseAnnotation(label_id=3, belongs_to=c, value_str='c').save()

        print(c.get_annotations())

        labels = c.get_annotation_labels()

        print(labels)

        self.assertEqual(len(labels), 2, 'Invalid number of labels')
        self.assertTrue('user/private-label' in labels, 'Missing label')
        self.assertTrue('user/private-label-many-values' in labels, 'Missing label')
        self.assertTrue(len(labels['user/private-label-many-values'].annotations), 3)

    def test_overlapping_markers(self):
        c = Case.objects.get(pk=1)
        l = AnnotationLabel(name='foo', owner_id=1, many_annotations_per_label=True)
        l.save()

        text = '01234567890123456789'
        print(text[0:10])
        print(text[10:10])

        # Valid markers
        for m in [
            CaseMarker(label=l, belongs_to=c, value_str='A', start=0, end=10),
            CaseMarker(label=l, belongs_to=c, value_str='B', start=10, end=10),
            CaseMarker(label=l, belongs_to=c, value_str='C', start=20, end=25),
        ]:
            m.clean()
            m.save()

        # Try invalid markers
        with self.assertRaises(ValidationError) as context:
            m = CaseMarker(label=l, belongs_to=c, value_str='invalid start>end', start=40, end=35)
            m.clean()
        print(context.exception)

        with self.assertRaises(ValidationError) as context:
            m = CaseMarker(label=l, belongs_to=c, value_str='overlaps with A,B,C', start=5, end=35)
            m.clean()
        print(context.exception)

        with self.assertRaises(ValidationError) as context:
            m = CaseMarker(label=l, belongs_to=c, value_str='overlaps with B', start=10, end=11)
            m.clean()
        print(context.exception)


    @skip
    def test_html_selector(self):
        with open(os.path.join(RESOURCE_DIR, '../templates/annotations/test.html')) as f:
            print()
            html_str = f.read()

            tree = lxml.html.fromstring(html_str)
            # json_str = '{"start":{"selector":"div>p:nth-of-type(2)","textNodeIndex":0,"offset":0},"end":{"selector":"div>p:nth-of-type(2)","textNodeIndex":0,"offset":35}}'
            # json_str = '{"start":{"selector":"div>p:nth-of-type(2)","textNodeIndex":2,"offset":1},"end":{"selector":"div>p:nth-of-type(2)","textNodeIndex":2,"offset":28}}'
            json_str = '{"start":{"selector":"div>h2:nth-of-type(2)","textNodeIndex":0,"offset":4},"end":{"selector":"div>h2:nth-of-type(2)","textNodeIndex":0,"offset":10}}'
            json_str = '{"start":{"selector":"div>p:nth-of-type(2)","textNodeIndex":2,"offset":1},"end":{"selector":"div>p:nth-of-type(2)","textNodeIndex":2,"offset":6}}'
            x = json.loads(json_str)

            start = x['start']
            end = x['end']
            selected_text = None

            if start['selector'] == end['selector']:

                start_matches = CSSSelector(start['selector'])(tree)

                if len(start_matches) == 1:
                    if start['textNodeIndex'] == 0 and end['textNodeIndex'] == 0:
                        selected_text = start_matches[0].text[start['offset']:end['offset']]

                        # replace text with {annotation}text{annotation}
                    else:

                        print('textNodeIndex != 0')
                        start_matches = CSSSelector(start['selector'])(tree)

                        for child in start_matches[0].getchildren():
                            print('Text: %s ' % child.text)
                            print('Tail: %s' % child.tail)

                            selected_text = child.tail[start['offset']:end['offset']]

                elif len(start_matches) > 1:
                    raise ValueError('Multiple start matches found')
                else:
                    raise ValueError('Start node does not exist')

                # for elem in :
                #     print(lxml.html.tostring(elem))
                #     print('Text: %s' % elem.text)
                #     print('Tail: %s' % elem.tail)
                #
                #     res = elem.text[x['start']]
                #
                #     print('---\nChildren')
                #
                #
                #     for c in elem.getchildren():
                #         print('Text: %s ' % c.text)
                #         print('Tail: %s' % c.tail)


            else:
                raise ValueError('start != end selector')


            print('Selected text: %s' % selected_text)

            # Processed tree -> HTML
            # Extract annotation markers with positions

            # for elem in CSSSelector(x['end']['selector'])(tree):
            #     print(lxml.html.tostring(elem))
