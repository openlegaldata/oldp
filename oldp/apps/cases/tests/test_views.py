from django.test import LiveServerTestCase
from django.urls import reverse


class CasesViewsTestCase(LiveServerTestCase):
    fixtures = ['courts.json']

    def test_index(self):
        res = self.client.get(reverse('cases:index'))

        self.assertEqual(res.status_code, 200)

