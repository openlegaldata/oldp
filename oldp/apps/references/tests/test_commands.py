from django.core.management import call_command
from django.test import TestCase, tag


@tag('commands')
class ReferencesCommandsTestCase(TestCase):

    def test_assign_references(self):
        call_command('assign_references', *[], **{})
