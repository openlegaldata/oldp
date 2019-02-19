import json
import logging
import os
import shutil

from django.conf import settings
from django.core.management import BaseCommand
from django.core.paginator import Paginator

from oldp.api.urls import router

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    """
    Export data to JSON using API serializers
    """
    help = 'Export API data as JSON'
    chunk_size = 1000

    def __init__(self):
        super(Command, self).__init__()

    def add_arguments(self, parser):

        parser.add_argument('output', type=str, help='Path relative to working directory ({})'.format(settings.WORKING_DIR))

        parser.add_argument('--override', action='store_true', default=False, help='Override existing output files')

        parser.add_argument('--limit', type=int, default=0,
                            help='Max. number of references per content type (default: 0, 0=unlimited)')

    def handle(self, *args, **opts):
        dir_path = os.path.join(settings.WORKING_DIR, opts['output'])

        if os.path.exists(dir_path):
            if opts['override']:
                shutil.rmtree(dir_path)
            else:
                logger.error('Output directory exist already: %s' % dir_path)
                return

        os.mkdir(dir_path)

        for api_register in router.registry:
            plural, view_set_cls, singular = api_register

            if '/' in plural or plural == 'users':
                logger.debug('Skip non-root endpoints (and users): %s' % plural)
                continue

            file_path = os.path.join(dir_path, plural + '.json')
            # view_set_cls = CaseViewSet
            view_set = view_set_cls()
            serializer_cls = view_set.get_serializer_class()
            # serializer = serializer_cls()
            qs = view_set.get_queryset()

            logger.debug('Writing to %s' % file_path)

            with open(file_path, 'w') as file:
                # Use paginator to not load all rows at once in memory
                paginator = Paginator(qs, self.chunk_size)
                for page in range(1, paginator.num_pages + 1):
                    logger.debug('%s - total %i - page %i / %i' % (plural, paginator.count, page, paginator.num_pages))

                    # Iterate over items and convert to JSON
                    for item in paginator.page(page).object_list:
                        data = serializer_cls(instance=item).data

                        # Append to file
                        file.write(json.dumps(data) + '\n')

        logger.info('Done')

