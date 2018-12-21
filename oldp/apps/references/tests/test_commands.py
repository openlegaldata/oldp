from django.core.management import call_command
from django.test import tag, TransactionTestCase


@tag('commands')
class ReferencesCommandsTestCase(TransactionTestCase):

    def test_assign_references(self):
        call_command('assign_references', *[], **{})
