import logging

from django.test import TestCase, tag

from oldp.apps.cases.models import Case
from oldp.apps.references.models import CaseReferenceMarker, ReferenceFromCase
from oldp.apps.references.models import Reference

logger = logging.getLogger(__name__)


@tag('models')
class ReferencesModelsTestCase(TestCase):
    fixtures = [
        'locations/countries.json', 'locations/states.json', 'locations/cities.json', 'courts/courts.json',
        'cases/cases.json'
    ]

    def setUp(self):
        pass

    def tearDown(self):
        pass

    def test_m2m(self):
        c1 = Case.objects.get(pk=1)
        c2 = Case.objects.get(pk=2)

        r1 = Reference(case=c2, to='case2-1')
        r1.save()

        marker = CaseReferenceMarker(text='foo', referenced_by=c1)
        marker.save()

        ReferenceFromCase.objects.create(reference=r1, marker=marker)
        ReferenceFromCase.objects.create(reference=Reference.objects.create(case=c2, to='case2'), marker=marker)

        self.assertEqual(2, len(marker.references.all()), 'Invalid number of references')
        self.assertEqual(2, Reference.objects.filter(casereferencemarker=marker).count(),
                         'Invalid number of references (reverse look-up)')

        self.assertEqual(1, r1.casereferencemarker_set.count(), 'Reverse set lookup failed')

        self.assertEqual(r1.get_marker(), marker, 'Invalid marker')

    def test_get_absolute_url(self):

        c1 = Case.objects.get(pk=1)
        r1 = Reference(case=c1, to='case2-1')

        self.assertEqual(r1.get_absolute_url(), c1.get_absolute_url(), 'Invalid url')
