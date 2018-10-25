import logging

from django.core.management import BaseCommand

from oldp.apps.laws.models import LawBook

LAW_BOOK_ORDER = {
    'bgb': 10,
    'gg': 10,
    'bafog': 9,
    'zpo': 9,
    'stgb': 9,
    'stpo': 9,
    'hgb': 9,
    'inso': 8,
    'weg': 8,
    'baugb': 8,
    'agg': 8,
    'urhg': 8,
    'dsgvo': 8,
}

# Get an instance of a logger
logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Assign predefined order values to law books based on slug'

    def __init__(self):
        super(Command, self).__init__()

    def handle(self, *args, **options):
        order_mapping = LAW_BOOK_ORDER

        for book_slug in order_mapping:

            updates = LawBook.objects.filter(slug=book_slug).update(order=order_mapping[book_slug])

            if updates > 0:
                logger.info('Updated %s' % book_slug)
            else:
                logger.debug('Does not exist: %s' % book_slug)

        logger.info('done')
