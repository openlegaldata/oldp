from django.core.management import call_command
from django.test import TestCase


class HomepageTests(TestCase):

    def test_render_imprint(self):
        call_command('render_imprint', *[], **{})
