from django.test import tag
from django.urls import reverse

from oldp.apps.lib.tests import ExtendedLiveServerTestCase


@tag('views')
class CourtsViewsTestCase(ExtendedLiveServerTestCase):
    fixtures = [
        'locations/countries.json',
        'locations/states.json',
        'locations/cities.json',
        'courts/courts.json',
    ]

    def test_index(self):
        res = self.client.get(reverse('courts:index'))

        self.assertContains(res, 'Amtsgericht Aalen')
        self.assertContains(res, 'EuGH')
        self.assertContains(res, 'Unknown state')

    def test_index_filter(self):
        res = self.client.get(reverse('courts:index') + '?state=1')

        self.assertNotContains(res, 'Amtsgericht Aalen')
        self.assertContains(res, 'EuGH')
        self.assertContains(res, 'Unknown court')

        self.assertStringOrder(res, 'EuGH', 'Unknown court')

        # With reverse order
        res = self.client.get(reverse('courts:index') + '?o=-name')
        self.assertStringOrder(res, 'Unknown court', 'EuGH')


    def test_detail(self):
        res = self.client.get(reverse('courts:detail', args=('ag-aalen',)))

        self.assertContains(res, 'Amtsgericht Aalen')
        self.assertContains(res, 'AGAALEN')

        # TODO test for cases
