from django.core.management import call_command
from django.test import TestCase, tag


@tag('commands')
class HomepageCommandsTestCase(TestCase):

    def test_set_law_book_order(self):
        call_command('render_html_pages', *[], **{})
