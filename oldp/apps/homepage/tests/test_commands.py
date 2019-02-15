from django.core.management import call_command
from django.test import TestCase, tag


@tag('commands')
class HomepageCommandsTestCase(TestCase):

    def test_dump_api_data(self):
        call_command('dump_api_data', *['api_dump_dir'], **{'override': True})

    def test_render_html_pages(self):
        call_command('render_html_pages', *[], **{})
