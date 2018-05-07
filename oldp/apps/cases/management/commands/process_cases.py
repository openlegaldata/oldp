import os

from django.conf import settings
from django.core.management.base import BaseCommand

from oldp.apps.backend.processing.processing_steps.post.send_to_es import SendToES
from oldp.apps.cases.models import Case
from oldp.apps.cases.processing.case_processor import CaseProcessor, CaseInputHandlerFS, CaseInputHandlerDB
from oldp.apps.cases.processing.openjur.openjur2es import OpenJurCaseInputHandlerFS
from oldp.apps.cases.processing.processing_steps.assign_court import AssignCourt
from oldp.apps.cases.processing.processing_steps.assign_topics import AssignTopics
from oldp.apps.cases.processing.processing_steps.extract_refs import ExtractRefs


class Command(BaseCommand):
    help = 'Processes cases from FS or DB with different processing steps (extract refs, ...)'

    def add_arguments(self, parser):
        parser.add_argument('step', nargs='*', type=str, help='Processing steps (extract_refs, assign_court, ...)')

        parser.add_argument('--input', nargs='+', type=str, default=os.path.join(settings.BASE_DIR, 'workingdir', 'cases'))
        parser.add_argument('--input-handler', type=str, default='fs', help='Read input from file system')

        parser.add_argument('--limit', type=int, default=20)
        parser.add_argument('--start', type=int, default=0)

        parser.add_argument('--max-lines', type=int, default=-1)

        parser.add_argument('--source', type=str, default='serializer',
                            help='When reading from FS process files differently (openjur, serializer)')

        parser.add_argument('--empty', action='store_true', default=False, help='Empty existing index')

        CaseProcessor.set_parser_arguments(parser)
        SendToES.set_parser_arguments(parser)

    def handle(self, *args, **options):

        indexer = CaseProcessor()
        indexer.set_options(options)

        # Define input
        if options['input_handler'] == 'fs':
            if options['source'] == 'openjur':
                handler = OpenJurCaseInputHandlerFS(limit=options['limit'], start=options['start'],
                                                    selector=options['input'])
            elif options['source'] == 'serializer':
                handler = CaseInputHandlerFS(limit=options['limit'], start=options['start'], selector=options['input'])
            else:
                raise ValueError('Mode not supported. Use openjur or serializer.')

        elif options['input_handler'] == 'db':
            handler = CaseInputHandlerDB(limit=options['limit'])

        else:
            raise ValueError('Unsupported input handler: %s' % options['input_handler'])

        indexer.set_input_handler(handler)

        # Prepare processing steps
        if 'assign_courts' in options['step']:
            indexer.processing_steps.append(AssignCourt())

        if 'extract_refs' in options['step']:  # TODO for default: or not options['step']
            indexer.processing_steps.append(ExtractRefs())

        if 'assign_topics' in options['step']:
            indexer.processing_steps.append(AssignTopics())

        # Prepare post processing steps
        if options['es']:
            es = SendToES()
            es.content_types = [Case]
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
