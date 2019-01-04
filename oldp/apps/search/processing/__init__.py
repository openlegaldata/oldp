import logging

from django.db.models.base import ModelBase
from haystack.models import SearchResult
from haystack.query import SearchQuerySet

from oldp.apps.laws.models import Law

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
        mlt_results = sqs.more_like_this(item)
        saved = []
        for result in mlt_results:  # type: SearchResult

            rel = self.model_relation(score=result.score)
            rel.set_relation(seed_id=item.pk, related_id=result.pk)
            rel.save()

            logger.debug('Saved %s' % rel)

            saved.append(rel)

        return saved

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
