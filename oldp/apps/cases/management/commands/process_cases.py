import os

from django.conf import settings
from django.core.management.base import BaseCommand

from oldp.apps.cases.processing.case_processor import CaseProcessor, CaseInputHandlerFS, CaseInputHandlerDB


class Command(BaseCommand):
    help = 'Processes cases from FS or DB with different processing steps (extract refs, ...)'
    indexer = CaseProcessor()

    def add_arguments(self, parser):
        self.indexer.set_parser_arguments(parser)
        CaseInputHandlerDB.set_parser_arguments(parser)

        parser.add_argument('--input', nargs='+', type=str, default=os.path.join(settings.BASE_DIR, 'workingdir', 'cases'))
        parser.add_argument('--input-handler', type=str, default='db',
                            help='Read input from this source (file system or database)', choices=['db', 'fs'])

        parser.add_argument('--max-lines', type=int, default=-1)

        parser.add_argument('--source', type=str, default='serializer',
                            help='When reading from FS process files differently (serializer)')

        parser.add_argument('--empty', action='store_true', default=False, help='Empty existing index')

    def handle(self, *args, **options):

        self.indexer.set_options(options)

        # Define input
        if options['input_handler'] == 'fs':
            if options['source'] == 'serializer':
                handler = CaseInputHandlerFS(limit=options['limit'], start=options['start'], selector=options['input'])
            else:
                raise ValueError('Mode not supported. Use openjur or serializer.')

        elif options['input_handler'] == 'db':
            handler = CaseInputHandlerDB(
                limit=options['limit'],
                start=options['start'],
                filter_qs=options['filter'],
                exclude_qs=options['exclude'],
                order_by=options['order_by'],
                per_page=options['per_page'],
            )

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
