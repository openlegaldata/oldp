import os

from django.conf import settings
from django.core.management.base import BaseCommand

from oldp.apps.backend.processing.processing_steps.post.send_to_es import SendToES
from oldp.apps.laws.models import Law
from oldp.apps.laws.processing.law_processor import LawProcessor, LawInputHandlerFS, LawInputHandlerDB
from oldp.apps.laws.processing.processing_steps.extract_refs import ExtractRefs
from oldp.apps.laws.processing.processing_steps.extract_topics import ExtractTopics

"""

Demo setup
--min-lines 1000
--limit 100

Re-process laws: ./manage.py process_laws --limit 10 --input-handler db extract_refs

"""


class Command(BaseCommand):
    help = 'Processes law XML files (and adds them to database)'

    def add_arguments(self, parser):
        parser.add_argument('step', nargs='*', type=str, help='Processing steps (extract_refs, ...)')

        parser.add_argument('--input', nargs='+', type=str,
                            default=os.path.join(settings.BASE_DIR, 'workingdir/gesetze-tools/laws'))
        # parser.add_argument('--filename', nargs='+', type=str)
        parser.add_argument('--input-handler', type=str, default='fs', help='Read input from file system')

        parser.add_argument('--min-lines', type=int, default=-1)
        parser.add_argument('--max-lines', type=int, default=-1)
        parser.add_argument('--limit', type=int, default=0)

        parser.add_argument('--empty', action='store_true', default=False, help='Emptys existing index')

        SendToES.set_parser_arguments(parser)
        LawProcessor.set_parser_arguments(parser)

    def handle(self, *args, **options):

        indexer = LawProcessor()
        indexer.set_options(options)

        # Define input
        if options['input_handler'] == 'fs':
            handler = LawInputHandlerFS(limit=options['limit'], selector=options['input'])
            handler.min_lines = options['min_lines']
            handler.max_lines = options['max_lines']

        elif options['input_handler'] == 'db':
            handler = LawInputHandlerDB(limit=options['limit'])

        else:
            raise ValueError('Unsupported input handler: %s' % options['input_handler'])

        indexer.set_input_handler(handler)

        # Prepare processing steps
        if 'extract_refs' in options['step']:  # TODO for default: or not options['step']
            indexer.processing_steps.append(ExtractRefs())

        if 'extract_topics' in options['step']:
            indexer.processing_steps.append(ExtractTopics())

        # Prepare post processing steps
        if options['es']:
            es = SendToES()
            es.content_types = [Law]
            es.set_es_url(options['es_url'])

            if options['es_setup']:
                es.setup_index()

            if options['empty'] and not options['es_setup']:
                es.empty_content()

            indexer.post_processing_steps.append(es)

        if options['empty']:
            indexer.empty_content()

        # Do processing
        indexer.process()
        indexer.log_stats()
