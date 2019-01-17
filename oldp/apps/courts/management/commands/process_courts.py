from django.core.management.base import BaseCommand

from oldp.apps.courts.processing.court_processor import CourtInputHandlerDB, CourtProcessor


class Command(BaseCommand):
    help = 'Processes courts from DB with different processing steps (enrich, ...)'
    indexer = CourtProcessor()

    def add_arguments(self, parser):
        self.indexer.set_parser_arguments(parser)
        CourtInputHandlerDB.set_parser_arguments(parser)

        # parser.add_argument('--empty', action='store_true', default=False, help='Empty existing index')

    def handle(self, *args, **options):
        self.indexer.set_options(options)

        # Define input
        handler = CourtInputHandlerDB(
                limit=options['limit'],
                start=options['start'],
                filter_qs=options['filter'],
                exclude_qs=options['exclude'],
                order_by=options['order_by'])

        self.indexer.set_input_handler(handler)

        # Prepare processing steps
        self.indexer.set_processing_steps(options['step'])

        # Do processing
        self.indexer.process()
        self.indexer.log_stats()
