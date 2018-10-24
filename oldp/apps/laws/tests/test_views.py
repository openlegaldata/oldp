from django.test import LiveServerTestCase, tag
from django.urls import reverse


@tag('views')
class LawsViewsTestCase(LiveServerTestCase):
    fixtures = ['laws/laws.json']

    def test_index(self):
        res = self.client.get(reverse('laws:index'))

        self.assertContains(res, 'Grundgesetz')
        self.assertContains(res, 'aappro-2002')

    def test_index_char(self):
        res = self.client.get(reverse('laws:index_char', args=('g', )))

        self.assertContains(res, 'Grundgesetz')

    def test_book(self):
        res = self.client.get(reverse('laws:book', args=('gg', )))

        self.assertContains(res, 'Grundgesetz')

    def test_book_revision(self):
        res = self.client.get(reverse('laws:book', args=('gg',)) + '?revision_date=2010-07-26')

        self.assertContains(res, 'Grundgesetz')

    def test_law(self):
        res = self.client.get(reverse('laws:law', args=('gg', 'artikel-1')))

        self.assertContains(res, 'Die nachfolgenden Grundrechte binden Gesetzgebung, vollziehende Gewalt und '
                                 'Rechtsprechung als unmittelbar geltendes Recht')
