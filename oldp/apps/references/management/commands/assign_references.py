import logging

from django.core.management import BaseCommand
from refex.models import RefType

# Get an instance of a logger
from oldp.apps.references.processing.processing_steps.assign_refs import ProcessingStep

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Assign references to corresponding database items (laws and cases)'

    def __init__(self):
        super(Command, self).__init__()

    def add_arguments(self, parser):

        parser.add_argument('--type', type=str, default='')

        parser.add_argument('--verbose', action='store_true', default=False)

        parser.add_argument('--override', action='store_true', default=False, help='Reassign all references')
        # parser.add_argument('--empty', action='store_true', default=False, help='Empty existing index')

        parser.add_argument('--limit', type=int, default=0)

    def handle(self, *args, **options):
        if options['verbose']:
            logger.setLevel(logging.DEBUG)

        processor = ProcessingStep()

        if options['type'] == '':
            # Use both reference types
            processor.assign_refs(RefType.LAW, options['limit'], options['override'])
            processor.assign_refs(RefType.CASE, options['limit'], options['override'])

        elif options['type'] == 'law':
            processor.assign_refs(RefType.LAW, options['limit'], options['override'])

        elif options['type'] == 'case':
            processor.assign_refs(RefType.CASE, options['limit'], options['override'])

        else:
            raise ValueError('Unsupported ref type: %s' % options['type'])
