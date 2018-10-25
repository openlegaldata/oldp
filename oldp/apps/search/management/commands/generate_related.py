import logging

from django.core.management import BaseCommand
from django.db.models.base import ModelBase
from haystack.models import SearchResult
from haystack.query import SearchQuerySet

from oldp.apps.cases.models import Case, RelatedCase
from oldp.apps.laws.models import Law, RelatedLaw

# Get an instance of a logger
logger = logging.getLogger(__name__)


class RelatedContentFinder(object):
    model = None
    model_relation = None

    def __init__(self, model: ModelBase, model_relation: ModelBase):
        super(RelatedContentFinder, self).__init__()

        if not type(model) == ModelBase:
            raise TypeError('model needs to be django DB model (ModelBase type)')

        if not type(model_relation) == ModelBase:
            raise TypeError('model_relation needs to be django DB model (ModelBase type)')

        self.model = model
        self.model_relation = model_relation

    def handle_item(self, item):
        """Perform MLT-query on item"""
        sqs = SearchQuerySet().models(self.model)
        for result in sqs.more_like_this(item):  # type: SearchResult

            rel = self.model_relation(score=result.score)
            rel.set_relation(seed_id=item.pk, related_id=result.pk)
            rel.save()

            logger.debug('Saved %s' % rel)

    def handle(self, options):
        items = self.model.objects.filter().order_by('-updated_date')

        if self.model == Law:
            items = items.exclude(book__latest=False)

        if options['limit'] > 0:
            items = items[:options['limit']]

        if options['empty']:
            self.model_relation.objects.all().delete()

        if len(items) < 1:
            logger.info('No content available')

        for item in items:
            self.handle_item(item)

        logger.info('done')


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

