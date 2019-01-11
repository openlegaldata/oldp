from django.test import tag
from django.urls import reverse

from oldp.apps.cases.models import Case
from oldp.apps.lib.tests import ExtendedLiveServerTestCase


@tag('views')
class CasesViewsTestCase(ExtendedLiveServerTestCase):
    fixtures = [
        'locations/countries.json',
        'locations/states.json',
        'locations/cities.json',
        'courts/courts.json',
        'cases/cases.json'
    ]

    def test_index(self):
        res = self.client.get(reverse('cases:index'))

        self.assertEqual(res.status_code, 200)

        self.assertContains(res, 'another-awesome-case')
        self.assertContains(res, 'foo-case')

        self.assertStringOrder(res, 'foo-case', 'another-awesome-case')

    def test_index_filter(self):
        res = self.client.get(reverse('cases:index') + '?court__state=1')

        self.assertNotContains(res, 'another-awesome-case')
        self.assertContains(res, 'foo-case')


    def test_detail(self):
        item = Case.objects.get(pk=1)

        res = self.client.get(item.get_absolute_url())

        self.assertEqual(res.status_code, 200)

    def test_short_url(self):
        item = Case.objects.get(pk=1)

        res = self.client.get(item.get_short_url())

        self.assertRedirects(res, item.get_absolute_url(), status_code=301)
