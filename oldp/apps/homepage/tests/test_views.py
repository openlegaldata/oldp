from django.conf import settings
from django.test import TestCase, tag


@tag('views')
class HomepageViewsTestCase(TestCase):
    fixtures = [
    ]

    def test_index(self):
        res = self.client.get('/')

        self.assertContains(res, settings.SITE_TITLE)

    def test_sitemaps(self):
        res = self.client.get('/sitemap.xml')

        self.assertContains(res, 'sitemap-court.xml')
        self.assertContains(res, 'sitemap-case.xml')
        self.assertContains(res, 'sitemap-law.xml')
