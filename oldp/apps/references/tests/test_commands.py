from django.core.management import call_command
from django.test import tag, TransactionTestCase


@tag('commands')
class ReferencesCommandsTestCase(TransactionTestCase):
    fixtures = [
        'courts/default.json',
        'cases/case_with_references.json',
        'laws/empty_bgb.json',
        'references/markers.json',
    ]

    def test_assign_references(self):
        call_command('assign_references', *[], **{})

    def test_dump_references(self):
        call_command('dump_references', *['references.csv'], **{'override': True})

    def test_dump_references_gephi(self):
        call_command('dump_references', *['references.csv'], **{'gephi': True, 'override': True})
