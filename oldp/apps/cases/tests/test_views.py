from django.test import LiveServerTestCase, tag
from django.urls import reverse

from oldp.apps.cases.models import Case


@tag('views')
class CasesViewsTestCase(LiveServerTestCase):
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

    def test_detail(self):
        item = Case.objects.get(pk=1)

        res = self.client.get(item.get_absolute_url())

        self.assertEqual(res.status_code, 200)

    def test_short_url(self):
        item = Case.objects.get(pk=1)

        res = self.client.get(item.get_short_url())

        self.assertRedirects(res, item.get_absolute_url(), status_code=301)
