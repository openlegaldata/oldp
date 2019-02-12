from django.test import TestCase

from oldp.apps.nlp.preprocessing import HtmlConcealer


class PreprocessingTestCase(TestCase):

    def test_html_concealing(self):
        html = '<h2>Tenor</h2>\n\n<ul class="ol"><li><p>1. Unter Ab&#228;nderung des Beschlusses der Kammer'
        concealer = HtmlConcealer(html)
        concealer.conceal()
        self.assertEqual('Tenor  1. Unter Abänderung des Beschlusses der Kammer', concealer.get_content())

    def test_html_concealing_pos_table(self):
        html = '<h2>Tenor</h2>\n\n<ul class="ol"><li><p>1. Unter Ab&#228;nderung des Beschlusses der Kammer'
        concealer = HtmlConcealer(html)
        concealer.conceal()
        concealed_word = concealer.get_content()[16:26]
        html_word = html[47:62]
        self.assertEqual(concealed_word, 'Abänderung')
        self.assertEqual(html_word, 'Ab&#228;nderung')
        self.assertEqual(concealer.concealed_to_html_pos(16, 26), (47, 62))
