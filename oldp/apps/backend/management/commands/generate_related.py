import json
import logging

import requests
from django.conf import settings
from django.core.management import BaseCommand
from django.db.models.base import ModelBase

from oldp.apps.cases.models import Case, RelatedCase
from oldp.apps.laws.models import Law, RelatedLaw

# Get an instance of a logger
logger = logging.getLogger(__name__)


class RelatedContentFinder(object):
    model = None
    model_relation = None
    es_index = settings.ES_INDEX
    es_url = settings.ES_URL
    es_type = None
    mlt_fields = None
    mlt_min_term_freq = 1
    mlt_max_query_terms = 12

    def __init__(self, model: ModelBase, model_relation: ModelBase, es_type: str, mlt_fields: list, es_index=None,
                 es_url=None):
        super(RelatedContentFinder, self).__init__()

        if not type(model) == ModelBase:
            raise TypeError('model needs to be django DB model (ModelBase type)')

        if not type(model_relation) == ModelBase:
            raise TypeError('model_relation needs to be django DB model (ModelBase type)')

        self.model = model
        self.model_relation = model_relation
        self.es_type = es_type
        self.mlt_fields = mlt_fields

        if es_index is not None:
            self.es_index = es_index

        if es_url is not None:
            self.es_url = es_url

    def handle_mlt_response(self, item, res):
        if res.status_code == 200:
            res_obj = res.json()
            hits = res_obj['hits']['hits']
            if hits:
                for hit in hits:
                    # logger.debug('Related hit: %s' % hit)
                    # print(hit['_score'])
                    rel = self.model_relation(score=hit['_score'])
                    rel.set_relation(seed_id=item.id, related_id=hit['_id'])
                    rel.save()

                    logger.debug('Saved %s' % rel)
            else:
                logger.warning('No MLT results for %s' % item)

                # print(res_obj)
        else:
            logger.error('Cannot retrieve MLT for %s' % item)

    def handle_item(self, item):
        query = {
            "query": {
                "more_like_this": {
                    "fields": self.mlt_fields,
                    # "fields": ["name.first", "name.last"],
                    "like": [
                        {
                            "_index": self.es_index,
                            "_type": self.es_type,
                            "_id": item.id
                        }
                    ],
                    "min_term_freq": self.mlt_min_term_freq,
                    "max_query_terms": self.mlt_max_query_terms
                }
            },
            "_source": ["title"]
        }
        query_url = self.es_url + '/' + self.es_type + '/_search'
        query_data = json.dumps(query)

        logger.debug('ES-MLT query url: %s' % query_url)
        logger.debug('ES-MLT query data: %s' % query_data)

        res = requests.get(query_url, data=query_data)

        self.handle_mlt_response(item, res)

    def handle(self, options):
        # TODO law exclude latested=False
        items = self.model.objects.filter().order_by('-updated_date')

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
        parser.add_argument('--empty', action='store_true', default=False, help='Emptys existing index')

    def handle(self, *args, **options):
        # TODO as processing step + admin action

        content_types = {
            'case': {
                'model': Case,
                'relation': RelatedCase,
                'es_type': 'case',
                'mlt_fields': ['text', 'title']
            },
            'law': {
                'model': Law,
                'relation': RelatedLaw,
                'es_type': 'law',
                'mlt_fields': ['text', 'title']
            }
        }

        if options['type'] in content_types:
            content_type = content_types[options['type']]

            logger.info('Generating related content for: %s' % content_type)

            RelatedContentFinder(content_type['model'], content_type['relation'], content_type['es_type'],
                                 content_type['mlt_fields']).handle(options)

        else:
            raise ValueError('Provided content type is not supports: %s. Use instead: %s' % (options['type'], content_types.keys()))

