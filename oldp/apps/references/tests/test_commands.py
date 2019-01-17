from django.core.management import call_command
from django.test import tag, TransactionTestCase


@tag('commands')
class ReferencesCommandsTestCase(TransactionTestCase):

    def test_assign_references(self):
        call_command('assign_references', *[], **{})

    def test_dump_references(self):
        call_command('dump_references', *['references.csv'], **{})
