import os

from django.conf import settings
from django.core.management.base import BaseCommand

from oldp.apps.laws.processing.law_processor import LawProcessor, LawInputHandlerFS, LawInputHandlerDB

"""

Demo setup
--min-lines 1000
--limit 100

Re-process laws: ./manage.py process_laws --limit 10 --input-handler db extract_refs

"""


class Command(BaseCommand):
    help = 'Processes law XML files (and adds them to database)'
    indexer = LawProcessor()

    def add_arguments(self, parser):
        self.indexer.set_parser_arguments(parser)
        LawInputHandlerDB.set_parser_arguments(parser)

        parser.add_argument('--input', nargs='+', type=str,
                            default=os.path.join(settings.BASE_DIR, 'workingdir/gesetze-tools/laws'))
        # parser.add_argument('--filename', nargs='+', type=str)
        parser.add_argument('--input-handler', type=str, default='fs', help='Read input from file system')

        parser.add_argument('--min-lines', type=int, default=-1)
        parser.add_argument('--max-lines', type=int, default=-1)

        parser.add_argument('--empty', action='store_true', default=False, help='Emptys existing index')


    def handle(self, *args, **options):

        self.indexer.set_options(options)

        # Define input
        if options['input_handler'] == 'fs':
            handler = LawInputHandlerFS(limit=options['limit'], selector=options['input'])
            handler.min_lines = options['min_lines']
            handler.max_lines = options['max_lines']

        elif options['input_handler'] == 'db':
            handler = LawInputHandlerDB(
                limit=options['limit'],
                start=options['start'],
                filter_qs=options['filter'],
                exclude_qs=options['exclude'],
                order_by=options['order_by'])

        else:
            raise ValueError('Unsupported input handler: %s' % options['input_handler'])

        self.indexer.set_input_handler(handler)

        # Prepare processing steps
        self.indexer.set_processing_steps(options['step'])

        if options['empty']:
            self.indexer.empty_content()

        # Do processing
        self.indexer.process()
        self.indexer.log_stats()
