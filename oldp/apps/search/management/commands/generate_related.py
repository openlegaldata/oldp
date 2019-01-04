import logging

from django.core.management import BaseCommand

from oldp.apps.cases.models import Case, RelatedCase
from oldp.apps.laws.models import Law, RelatedLaw
from oldp.apps.search.processing import RelatedContentFinder

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Assign related cases with MoreLikeThis results'

    def __init__(self):
        super(Command, self).__init__()

    def add_arguments(self, parser):
        parser.add_argument('type', type=str, help='Content type (case, law, ...)')
        parser.add_argument('--limit', type=int, default=20)
        parser.add_argument('--empty', action='store_true', default=False)

    def handle(self, *args, **options):
        # TODO as processing step + admin action

        content_types = {
            'case': {
                'model': Case,
                'relation': RelatedCase,
                # 'es_type': 'case',
                # 'mlt_fields': ['text', 'title']
            },
            'law': {
                'model': Law,
                'relation': RelatedLaw,
                # 'es_type': 'law',
                # 'mlt_fields': ['text', 'title']
            }
        }

        if options['type'] in content_types:
            content_type = content_types[options['type']]

            logger.info('Generating related content for: %s' % content_type)

            RelatedContentFinder(content_type['model'], content_type['relation']).handle(options)

        else:
            raise ValueError('Provided content type is not supports: %s. Use instead: %s' % (options['type'], content_types.keys()))

