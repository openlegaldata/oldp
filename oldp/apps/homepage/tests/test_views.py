from django.conf import settings
from django.test import TestCase


class HomepageViewsTestCase(TestCase):
    def test_index(self):
        res = self.client.get('/')

        self.assertContains(res, settings.SITE_TITLE)
